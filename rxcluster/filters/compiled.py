"""Compilation of :class:`FilterState` into a fast, immutable predicate.

Compilation happens once and the resulting :class:`CompiledFilter` is shared
between all clients that use an identical filter state (interning by
signature). This keeps the fan-out cost low even with many clients.
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Hashable

from ..grid import distance_km, grid_to_latlon
from ..models import SourceType, Spot, SpotKind
from .model import EXACT_CATEGORIES, FilterState

KNOWN_EVENTS = ("POTA", "SOTA", "IOTA", "WWFF", "LLOTA")

# Geography categories suspended while NEARBY is active.
GEO_CATEGORIES = frozenset(
    {"dxcont", "decont", "dxzone", "dezone", "dxdxcc", "dedxcc", "dxgrid2", "degrid2"}
)

# NEARBY is deliberately broader on the low bands.
LOW_BANDS = frozenset({"160m", "80m", "60m"})
NEARBY_RADIUS_LOW_KM = 1500.0
NEARBY_RADIUS_KM = 700.0


def _compile_patterns(patterns: list[str]) -> list[re.Pattern[str]]:
    compiled: list[re.Pattern[str]] = []
    for pat in patterns:
        regex = fnmatch.translate(pat.upper())
        compiled.append(re.compile(regex))
    return compiled


class CompiledFilter:
    """Immutable predicate deciding whether a spot passes for one client."""

    __slots__ = (
        "_allow",
        "_reject",
        "_allow_patterns",
        "_reject_patterns",
        "_comment_allow",
        "_comment_reject",
        "_min_snr",
        "_switches",
        "_operator",
        "_operator_grid",
        "_operator_pos",
        "_nearby",
    )

    def __init__(
        self, state: FilterState, operator_call: str = "", operator_grid: str = ""
    ) -> None:
        self._allow = {
            cat: (frozenset(v) if v is not None else None) for cat, v in state.allow.items()
        }
        self._reject = {cat: frozenset(v) for cat, v in state.reject.items()}
        self._allow_patterns = {
            cat: (_compile_patterns(v) if v is not None else None)
            for cat, v in state.allow_patterns.items()
        }
        self._reject_patterns = {
            cat: _compile_patterns(v) for cat, v in state.reject_patterns.items()
        }
        self._comment_allow = tuple(p.lower() for p in state.comment_allow)
        self._comment_reject = tuple(p.lower() for p in state.comment_reject)
        self._min_snr = {m.upper(): v for m, v in state.min_snr.items()}
        self._switches = dict(state.switches)
        self._operator = operator_call.upper()
        self._operator_grid = operator_grid.strip().upper()
        self._operator_pos = (
            grid_to_latlon(self._operator_grid) if self._operator_grid else None
        )
        self._nearby = bool(state.nearby)

    # -- category value extraction ----------------------------------------
    @staticmethod
    def _exact_value(category: str, spot: Spot) -> str:
        if category == "band":
            return spot.band.lower()
        if category == "mode":
            return spot.mode.value.lower()
        if category == "source":
            return spot.source_type.value.lower()
        if category == "dxcont":
            return spot.continent.lower()
        if category == "decont":
            return spot.spotter_continent.lower()
        if category == "dxzone":
            return str(spot.cq_zone) if spot.cq_zone is not None else ""
        if category == "dezone":
            return str(spot.spotter_cq_zone) if spot.spotter_cq_zone is not None else ""
        if category == "dxdxcc":
            return spot.dxcc.lower()
        if category == "dedxcc":
            return spot.spotter_dxcc.lower()
        if category == "dxgrid2":
            return spot.dx_grid[:2].lower()
        if category == "degrid2":
            return spot.spotter_grid[:2].lower()
        if category == "confidence":
            return spot.confidence.value.lower()
        if category == "path":
            return spot.path.value.lower()
        return ""

    @staticmethod
    def _events(spot: Spot) -> frozenset[str]:
        comment = spot.comment.upper()
        return frozenset(e for e in KNOWN_EVENTS if e in comment)

    def _match_patterns(self, patterns: list[re.Pattern[str]] | None, value: str) -> bool:
        if not patterns:
            return False
        up = value.upper()
        return any(p.match(up) for p in patterns)

    # -- DXCC matching (entity name or canonical prefix) -------------------
    def _dxcc_matches(self, category: str, spot: Spot, value: str) -> bool:
        if category == "dxdxcc":
            name, call = spot.dxcc.lower(), spot.dx_call.upper()
        else:
            name, call = spot.spotter_dxcc.lower(), spot.spotter.upper()
        if value.lower() == name:
            return True
        # Canonical prefix: match the leading characters of the callsign.
        return bool(value) and call.startswith(value.upper())

    # -- NEARBY ------------------------------------------------------------
    def _nearby_pass(self, spot: Spot) -> bool:
        # Without a valid operator grid NEARBY cannot be evaluated, so it stays
        # inert rather than black-holing every spot.
        if self._operator_pos is None:
            return True
        radius = NEARBY_RADIUS_LOW_KM if spot.band in LOW_BANDS else NEARBY_RADIUS_KM
        op_lat, op_lon = self._operator_pos
        for grid in (spot.dx_grid, spot.spotter_grid):
            target = grid_to_latlon(grid) if grid else None
            if target is None:
                continue
            if distance_km(op_lat, op_lon, target[0], target[1]) <= radius:
                return True
        return False

    # -- public predicate --------------------------------------------------
    def allows(self, spot: Spot) -> bool:
        switches = self._switches

        # Bulletin traffic is governed solely by its feature switch.
        if spot.kind is SpotKind.WWV:
            return switches.get("wwv", True)
        if spot.kind is SpotKind.WCY:
            return switches.get("wcy", True)
        if spot.kind is SpotKind.ANNOUNCE:
            return switches.get("announce", True)

        # Feature switches that apply to spots.
        if (spot.is_beacon or spot.kind is SpotKind.BEACON) and not switches.get(
            "beacon", False
        ):
            return False
        if spot.toxic and not switches.get("toxic", False):
            return False
        if self._operator and not switches.get("self", False):
            if spot.dx_call.upper() == self._operator:
                return False
        # Own callsign stays visible when SELF is on, regardless of NEARBY.
        if self._operator and switches.get("self", False):
            if spot.dx_call.upper() == self._operator:
                return True

        if self._nearby and not self._nearby_pass(spot):
            return False

        for cat in EXACT_CATEGORIES:
            if cat == "event":
                continue
            if self._nearby and cat in GEO_CATEGORIES:
                continue
            if cat in ("dxdxcc", "dedxcc"):
                rejected = self._reject.get(cat)
                if rejected and any(self._dxcc_matches(cat, spot, v) for v in rejected):
                    return False
                allowed = self._allow.get(cat)
                if allowed is not None and not any(
                    self._dxcc_matches(cat, spot, v) for v in allowed
                ):
                    return False
                continue
            value = self._exact_value(cat, spot)
            rejected = self._reject.get(cat)
            if rejected and value in rejected:
                return False
            allowed = self._allow.get(cat)
            if allowed is not None and value not in allowed:
                return False

        # Event tags.
        event_allow = self._allow.get("event")
        event_reject = self._reject.get("event")
        if event_allow is not None or event_reject:
            tags = self._events(spot)
            if event_reject and not tags.isdisjoint(event_reject):
                return False
            if event_allow is not None:
                # Untagged spots always pass the EVENT category.
                if tags and tags.isdisjoint(event_allow):
                    return False

        # Callsign patterns: true DX is always allowed regardless of filters.
        if self._operator and spot.dx_call.upper() == self._operator:
            return True
        if not self._patterns_pass("dxcall", spot.dx_call):
            return False
        if not self._patterns_pass("decall", spot.spotter):
            return False

        # Comment phrases.
        if self._comment_reject or self._comment_allow:
            comment = spot.comment.lower()
            if any(p in comment for p in self._comment_reject):
                return False
            if self._comment_allow and not any(p in comment for p in self._comment_allow):
                return False

        # Minimum SNR (skimmer spots with a known SNR only).
        if self._min_snr and spot.snr is not None and spot.source_type is SourceType.SKIMMER:
            threshold = self._min_snr.get(spot.mode.value.upper())
            if threshold is not None and spot.snr < threshold:
                return False

        return True

    def _patterns_pass(self, category: str, value: str) -> bool:
        up = value.upper()
        rej = self._reject_patterns.get(category)
        if rej and self._match_patterns(rej, up):
            return False
        allow = self._allow_patterns.get(category)
        if allow is not None and not self._match_patterns(allow, up):
            return False
        return True


# --------------------------------------------------------------------------
# Interning
# --------------------------------------------------------------------------
_intern_cache: dict[Hashable, CompiledFilter] = {}


def _signature(state: FilterState, operator_call: str, operator_grid: str) -> Hashable:
    def _norm(mapping: dict[str, set[str] | None]) -> tuple:
        return tuple(
            sorted((k, (frozenset(v) if v is not None else None)) for k, v in mapping.items())
        )

    def _norm_list(mapping: dict[str, list[str] | None]) -> tuple:
        return tuple(sorted((k, (tuple(v) if v is not None else None)) for k, v in mapping.items()))

    return (
        operator_call.upper(),
        operator_grid.strip().upper(),
        state.nearby,
        _norm(state.allow),
        _norm(state.reject),
        _norm_list(state.allow_patterns),
        _norm_list(state.reject_patterns),
        tuple(state.comment_allow),
        tuple(state.comment_reject),
        tuple(sorted(state.min_snr.items())),
        tuple(sorted(state.switches.items())),
    )


def compile_filter(
    state: FilterState, operator_call: str = "", operator_grid: str = ""
) -> CompiledFilter:
    """Compile (and intern) a :class:`CompiledFilter` for the given state."""
    sig = _signature(state, operator_call, operator_grid)
    cached = _intern_cache.get(sig)
    if cached is not None:
        return cached
    compiled = CompiledFilter(state, operator_call, operator_grid)
    _intern_cache[sig] = compiled
    if len(_intern_cache) > 4096:  # simple bound to avoid unbounded growth
        _intern_cache.clear()
        _intern_cache[sig] = compiled
    return compiled


_CATEGORY_LABELS: dict[str, str] = {
    "band": "BAND",
    "mode": "MODE",
    "source": "SOURCE",
    "dxcont": "DXCONT",
    "decont": "DECONT",
    "dxzone": "DXZONE",
    "dezone": "DEZONE",
    "dxdxcc": "DXDXCC",
    "dedxcc": "DEDXCC",
    "dxgrid2": "DXGRID2",
    "degrid2": "DEGRID2",
    "confidence": "CONFIDENCE",
    "path": "PATH",
    "event": "EVENT",
    "comment": "COMMENT",
}


def _format_exact(state: FilterState, cat: str) -> str:
    allow = state.allow.get(cat)
    reject = state.reject.get(cat)
    parts: list[str] = []
    if allow is None:
        parts.append("All")
    elif not allow:
        parts.append("None")
    else:
        parts.append(",".join(sorted(allow)))
    if reject:
        parts.append("block " + ",".join(sorted(reject)))
    return " ".join(parts) if parts else "All"


def describe(state: FilterState, category: str | None = None, full: bool = False) -> str:
    """Human-readable summary used by ``SHOW FILTER``.

    ``category`` restricts the output to one category; ``full`` renders the
    complete effective selections including switches and minimum SNR.
    """
    lines: list[str] = []
    cat = category.lower() if category else None

    def _want(name: str) -> bool:
        return cat is None or cat == name

    for exact in ("band", "mode", "source", "dxcont", "decont", "dxzone", "dezone",
                  "dxdxcc", "dedxcc", "dxgrid2", "degrid2", "confidence", "path", "event"):
        if _want(exact):
            lines.append(f"{_CATEGORY_LABELS[exact]:<12}{_format_exact(state, exact)}")
    if _want("dxcall"):
        allow = state.allow_patterns.get("dxcall")
        rej = state.reject_patterns.get("dxcall") or []
        text = "All" if allow is None else (",".join(allow) or "None")
        if rej:
            text += " block " + ",".join(rej)
        lines.append(f"{'DXCALL':<12}{text}")
    if _want("decall"):
        allow = state.allow_patterns.get("decall")
        rej = state.reject_patterns.get("decall") or []
        text = "All" if allow is None else (",".join(allow) or "None")
        if rej:
            text += " block " + ",".join(rej)
        lines.append(f"{'DECALL':<12}{text}")
    if _want("comment"):
        if state.comment_allow:
            lines.append("COMMENT-PASS " + ", ".join(state.comment_allow))
        if state.comment_reject:
            lines.append("COMMENT-REJECT " + ", ".join(state.comment_reject))
    if _want("minsnr"):
        if state.min_snr:
            lines.append(
                "MINSNR      " + ", ".join(f"{k}={v}" for k, v in sorted(state.min_snr.items()))
            )
        elif full:
            lines.append("MINSNR      None")
    if _want("nearby"):
        lines.append(f"{'NEARBY':<12}{'On' if state.nearby else 'Off'}")
    if _want("switches"):
        switches = ", ".join(
            f"{k}={'on' if v else 'off'}" for k, v in sorted(state.switches.items())
        )
        lines.append("SWITCHES    " + switches)
    return "\n".join(lines)
