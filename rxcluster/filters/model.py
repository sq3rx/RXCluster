"""Filter state model.

A :class:`FilterState` holds the per-client PASS/REJECT selections. The
semantics follow the N2WQ/GoCluster dialect:

* ``REJECT`` wins over ``PASS`` within a category.
* Categories are combined with logical AND.
* ``REJECT <cat> ALL`` restricts the category to nothing; a following
  ``PASS <cat> a,b`` re-adds values. ``PASS <cat> ALL`` clears restrictions.
* ``MODE`` naturally preserves visibility for modes that are not named.
* ``COMMENT`` matches literal, case-insensitive substrings; a rejected phrase
  wins over any allowed phrase.
* ``MINSNR`` applies a per-mode threshold and exempts human reports and spots
  without an SNR.

The state is compiled into a fast immutable :class:`~rxcluster.filters.compiled.CompiledFilter`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..config import DefaultFilterConfig

# Exact-value categories (membership testing against a set).
EXACT_CATEGORIES: tuple[str, ...] = (
    "band",
    "mode",
    "source",
    "dxcont",
    "decont",
    "dxzone",
    "dezone",
    "dxdxcc",
    "dedxcc",
    "dxgrid2",
    "degrid2",
    "confidence",
    "path",
    "event",
)

# Glob/pattern categories (wildcards allowed).
PATTERN_CATEGORIES: tuple[str, ...] = ("dxcall", "decall")

ALL_CATEGORIES: tuple[str, ...] = EXACT_CATEGORIES + PATTERN_CATEGORIES

SWITCH_NAMES: tuple[str, ...] = ("beacon", "wwv", "wcy", "announce", "self")

DEFAULT_SWITCHES: dict[str, bool] = {
    "beacon": False,
    "wwv": True,
    "wcy": True,
    "announce": True,
    "self": False,
}


@dataclass
class FilterState:
    """Mutable per-client filter selections."""

    # For exact categories: ``allow[cat] is None`` means unrestricted.
    allow: dict[str, set[str] | None] = field(
        default_factory=lambda: {c: None for c in EXACT_CATEGORIES}
    )
    reject: dict[str, set[str]] = field(
        default_factory=lambda: {c: set() for c in EXACT_CATEGORIES}
    )
    # For pattern categories: ``None`` means unrestricted.
    allow_patterns: dict[str, list[str] | None] = field(
        default_factory=lambda: {c: None for c in PATTERN_CATEGORIES}
    )
    reject_patterns: dict[str, list[str]] = field(
        default_factory=lambda: {c: [] for c in PATTERN_CATEGORIES}
    )
    comment_allow: list[str] = field(default_factory=list)
    comment_reject: list[str] = field(default_factory=list)
    min_snr: dict[str, int] = field(default_factory=dict)
    switches: dict[str, bool] = field(default_factory=lambda: dict(DEFAULT_SWITCHES))

    # -- mutations ---------------------------------------------------------
    def add_allow(self, category: str, values: list[str]) -> None:
        if category == "comment":
            self.comment_allow.extend(v.lower() for v in values)
            return
        if category in PATTERN_CATEGORIES:
            if any(v.lower() == "all" for v in values):
                self.allow_patterns[category] = None
                self.reject_patterns[category].clear()
                return
            current = self.allow_patterns[category]
            self.allow_patterns[category] = (list(current) if current else []) + values
            return
        lowered = [v.lower() for v in values]
        if any(v == "all" for v in lowered):
            self.allow[category] = None
            self.reject[category].clear()
            return
        current = self.allow[category]
        self.allow[category] = set(current) if current is not None else None
        if current is not None:
            self.allow[category].update(lowered)
        self.reject[category].difference_update(lowered)

    def add_reject(self, category: str, values: list[str]) -> None:
        if category == "comment":
            self.comment_reject.extend(v.lower() for v in values)
            return
        if category in PATTERN_CATEGORIES:
            if any(v.lower() == "all" for v in values):
                self.allow_patterns[category] = []
                self.reject_patterns[category] = []
                return
            self.reject_patterns[category].extend(values)
            return
        lowered = [v.lower() for v in values]
        if any(v == "all" for v in lowered):
            self.allow[category] = set()
            self.reject[category].clear()
            return
        self.reject[category].update(lowered)
        if self.allow[category] is not None:
            self.allow[category].difference_update(lowered)

    def clear_category(self, category: str) -> None:
        if category == "comment":
            self.comment_allow.clear()
            self.comment_reject.clear()
            return
        if category in PATTERN_CATEGORIES:
            self.allow_patterns[category] = None
            self.reject_patterns[category] = []
            return
        self.allow[category] = None
        self.reject[category].clear()

    def set_switch(self, name: str, value: bool) -> None:
        self.switches[name] = value

    def set_min_snr(self, mode: str, value: int | None) -> None:
        if value is None:
            self.min_snr.pop(mode, None)
        else:
            self.min_snr[mode] = value

    # -- serialization -----------------------------------------------------
    def to_dict(self) -> dict:
        """Return a JSON-serializable representation.

        ``None`` (unrestricted) and an empty selection are semantically
        different, so they are preserved distinctly: ``None`` stays ``None``
        while an empty selection becomes ``[]``.
        """

        def _exact(mapping: dict[str, set[str] | None]) -> dict[str, list[str] | None]:
            return {k: (None if v is None else sorted(v)) for k, v in mapping.items()}

        def _pattern(mapping: dict[str, list[str] | None]) -> dict[str, list[str] | None]:
            return {k: (None if v is None else list(v)) for k, v in mapping.items()}

        return {
            "allow": _exact(self.allow),
            "reject": {k: sorted(v) for k, v in self.reject.items()},
            "allow_patterns": _pattern(self.allow_patterns),
            "reject_patterns": {k: list(v) for k, v in self.reject_patterns.items()},
            "comment_allow": list(self.comment_allow),
            "comment_reject": list(self.comment_reject),
            "min_snr": {k: int(v) for k, v in self.min_snr.items()},
            "switches": {k: bool(v) for k, v in self.switches.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> FilterState:
        """Rebuild a :class:`FilterState` from :meth:`to_dict` output.

        Missing or malformed entries fall back to the category defaults so a
        stale or partially written file never breaks login.
        """
        state = cls()

        allow = data.get("allow")
        if isinstance(allow, dict):
            for cat in EXACT_CATEGORIES:
                if cat not in allow:
                    continue
                value = allow[cat]
                if value is None:
                    state.allow[cat] = None
                elif isinstance(value, list):
                    state.allow[cat] = {str(v).lower() for v in value}

        reject = data.get("reject")
        if isinstance(reject, dict):
            for cat in EXACT_CATEGORIES:
                value = reject.get(cat)
                if isinstance(value, list):
                    state.reject[cat] = {str(v).lower() for v in value}

        allow_patterns = data.get("allow_patterns")
        if isinstance(allow_patterns, dict):
            for cat in PATTERN_CATEGORIES:
                if cat not in allow_patterns:
                    continue
                value = allow_patterns[cat]
                if value is None:
                    state.allow_patterns[cat] = None
                elif isinstance(value, list):
                    state.allow_patterns[cat] = [str(v) for v in value]

        reject_patterns = data.get("reject_patterns")
        if isinstance(reject_patterns, dict):
            for cat in PATTERN_CATEGORIES:
                value = reject_patterns.get(cat)
                if isinstance(value, list):
                    state.reject_patterns[cat] = [str(v) for v in value]

        for key, attr in (("comment_allow", "comment_allow"), ("comment_reject", "comment_reject")):
            value = data.get(key)
            if isinstance(value, list):
                setattr(state, attr, [str(v) for v in value])

        min_snr = data.get("min_snr")
        if isinstance(min_snr, dict):
            for mode, value in min_snr.items():
                try:
                    state.min_snr[str(mode).upper()] = int(value)
                except (TypeError, ValueError):
                    continue

        switches = data.get("switches")
        if isinstance(switches, dict):
            for name in SWITCH_NAMES:
                if name in switches:
                    state.switches[name] = bool(switches[name])

        return state


def default_state_from_config(cfg: DefaultFilterConfig) -> FilterState:
    """Build a :class:`FilterState` from the configured node-level defaults."""
    state = FilterState()
    if cfg.bands != "all":
        state.add_reject("band", ["all"])
        state.add_allow("band", list(cfg.bands))
    if cfg.modes != "all":
        state.add_reject("mode", ["all"])
        state.add_allow("mode", list(cfg.modes))
    if cfg.reject_confidence:
        state.add_reject("confidence", list(cfg.reject_confidence))
    # Path: allow only the listed classes.
    if cfg.path:
        state.add_reject("path", ["all"])
        state.add_allow("path", list(cfg.path))
    for mode, value in cfg.min_snr.items():
        state.set_min_snr(mode.upper(), value)
    for name, value in cfg.switches.model_dump().items():
        state.set_switch(name, value)
    return state