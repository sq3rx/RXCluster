"""Telnet command parsing.

Supports the N2WQ/GoCluster dialect plus common CC Cluster / DX Spider
aliases so that N1MM Logger+ stored commands keep working.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from ..grid import is_valid_grid
from ..models import Mode
from ..validate.patterns import is_valid_shape
from .compiled import describe
from .model import ALL_CATEGORIES, DEFAULT_SWITCHES, EXACT_CATEGORIES, SWITCH_NAMES, FilterState

# Mapping from user-facing category tokens to internal category names.
_CATEGORY_ALIASES: dict[str, str] = {
    "BAND": "band",
    "MODE": "mode",
    "SOURCE": "source",
    "DXCALL": "dxcall",
    "DECALL": "decall",
    "DXCONT": "dxcont",
    "DECONT": "decont",
    # DX Spider / CC Cluster spelling of the DX continent filter.
    "CONT": "dxcont",
    "DXZONE": "dxzone",
    "DEZONE": "dezone",
    "DXDXCC": "dxdxcc",
    "DEDXCC": "dedxcc",
    "DXGRID2": "dxgrid2",
    "DEGRID2": "degrid2",
    "CONFIDENCE": "confidence",
    "CONF": "confidence",
    "PATH": "path",
    "COMMENT": "comment",
    "EVENT": "event",
}

# Categories whose values may contain spaces (DXCC entity names, comment
# phrases); these are split on commas only, not on whitespace.
_GROUPED_CATEGORIES = frozenset({"dxdxcc", "dedxcc", "comment"})

# ``SET/<SUB>`` continent aliases (CC Cluster / DX Spider). The ``NO``-prefixed
# entries clear the selection, the others behave like PASS.
_CONTI_SET_SUBS: dict[str, tuple[str, bool]] = {
    "CONT": ("dxcont", False),
    "DXCONT": ("dxcont", False),
    "DECONT": ("decont", False),
    "NOCONT": ("dxcont", True),
    "NODXCONT": ("dxcont", True),
    "NODECONT": ("decont", True),
}

# Characters allowed in a manually posted spot comment.
_POST_COMMENT_RE = re.compile(r"^[A-Za-z0-9 /#@\-.,*?_]*$")

_DEDUPE_POLICIES = ("FAST", "MED", "SLOW")

# Mode tokens accepted by SH/DX and their canonical Mode value. USB/LSB are
# rendered on the wire for SSB, so they map back to SSB for searching.
_SHOW_MODE_TOKENS: dict[str, str] = {
    "CW": "CW",
    "RTTY": "RTTY",
    "PSK": "PSK",
    "FT8": "FT8",
    "FT4": "FT4",
    "SSB": "SSB",
    "USB": "SSB",
    "LSB": "SSB",
}


@dataclass
class PostRequest:
    """A parsed ``DX`` posting command."""

    freq_khz: float
    dx_call: str
    comment: str


@dataclass
class DxQuery:
    """A parsed ``SH/DX`` (``SHOW DX``) read-back query."""

    count: int = 10
    dx_call: str = ""
    band: str = ""
    mode: str = ""


@dataclass
class CommandResult:
    handled: bool = False
    responses: list[str] = field(default_factory=list)
    changed: bool = False
    disconnect: bool = False
    pause_seconds: float = 0.0
    post: PostRequest | None = None


@dataclass
class CommandHandlers:
    """Optional callbacks wiring the parser to a live session/pipeline."""

    operator_call: str = ""
    operator_grid: str = ""
    recent_provider: Callable[[int], list[str]] | None = None
    recent_for_provider: Callable[[str, int], list[str]] | None = None
    # ``dx_provider`` handles the full ``SH/DX`` grammar (count, call/prefix,
    # band, mode); it is preferred over the two legacy providers above.
    dx_provider: Callable[[DxQuery], list[str]] | None = None
    # Band names accepted in ``SH/DX <band>`` (from the node band plan).
    band_names: frozenset[str] = frozenset()
    grid_setter: Callable[[str], None] | None = None
    noise_setter: Callable[[str], None] | None = None
    dedupe_setter: Callable[[str], None] | None = None
    dedupe_provider: Callable[[], str] | None = None
    prop_provider: Callable[[str, str, str], list[str]] | None = None
    whospotsme_provider: Callable[[str, str], list[str]] | None = None
    post_handler: Callable[[PostRequest], str] | None = None
    pause_setter: Callable[[int], str] | None = None
    resume_setter: Callable[[], str] | None = None
    hold_provider: Callable[[], str] | None = None
    # NEARBY is a session-level feature (operator grid + radius), not a filter
    # category, so it is wired through these callbacks.
    nearby_setter: Callable[[bool, float | None, float | None], str] | None = None
    nearby_provider: Callable[[], list[str]] | None = None
    # Supplies a fresh :class:`FilterState` holding the node-level defaults,
    # used by RESET to restore the login-time filter.
    default_state_provider: Callable[[], FilterState] | None = None


def _split_values(args: list[str]) -> list[str]:
    values: list[str] = []
    for chunk in args:
        for value in chunk.replace(",", " ").split():
            values.append(value)
    return values


def _split_grouped(args: list[str]) -> list[str]:
    """Split comma-separated values while preserving spaces inside each value.

    Used for free-text categories (DXCC entity names, COMMENT phrases) where a
    value may legitimately contain spaces, e.g. ``United States``.
    """
    joined = " ".join(args)
    return [value.strip() for value in joined.split(",") if value.strip()]


def _normalize_band(value: str) -> str:
    v = value.strip().lower()
    if v.isdigit():
        return v + "m"
    return v


def _normalize_values(category: str, values: list[str]) -> list[str]:
    if category == "band":
        return [_normalize_band(v) for v in values]
    if category in ("mode", "path", "confidence", "dxgrid2", "degrid2"):
        return [v.upper() for v in values]
    return [v.lower() for v in values]


def parse_command(
    line: str,
    state: FilterState,
    handlers: CommandHandlers | None = None,
) -> CommandResult:
    """Parse and (for mutating commands) apply a command to ``state``."""
    h = handlers or CommandHandlers()
    line = line.strip()
    if not line or line == " " or line == "\r":
        return CommandResult(handled=True)

    parts = line.split()
    head = parts[0].upper().split("/")
    verb = head[0]
    args = head[1:] + parts[1:]

    if verb in ("BYE", "QUIT", "EXIT"):
        return CommandResult(handled=True, disconnect=True)

    if verb in ("PASS", "REJECT"):
        return _parse_pass_reject(verb, args, state, h)

    if verb in ("RESET", "CLEAR"):
        return _parse_reset(args, state, h)

    if verb == "SET":
        return _parse_set(args, state, h)

    if verb in ("SHOW", "SH"):
        return _parse_show(args, state, h)

    if verb == "SHOWDX":
        return _parse_show(["DX", *args], state, h)

    if verb == "ACCEPT":
        # DX Spider uses ACCEPT/<CATEGORY> as the positive filter verb, e.g.
        # ACCEPT/CONT EU. A bare ACCEPT (or ACCEPT/SPOTS) resumes the feed.
        if args and args[0].upper() in _CATEGORY_ALIASES:
            return _parse_pass_reject("PASS", args, state, h)
        return CommandResult(handled=True, responses=["Spots resumed."])

    if verb == "DX":
        return _parse_dx(args, h)

    if verb == "PAUSE":
        return _parse_pause(args, h)

    if verb == "RESUME":
        if h.resume_setter is not None:
            return CommandResult(handled=True, responses=[h.resume_setter()])
        return CommandResult(handled=True, responses=["Live spots resumed."])

    if verb == "WHOSPOTSME":
        band = args[0].upper() if args else ""
        if h.whospotsme_provider is not None:
            return CommandResult(
                handled=True, responses=h.whospotsme_provider(band, h.operator_call)
            )
        return CommandResult(handled=True, responses=["No spotter history available."])

    if verb == "HELP":
        return _parse_help(args)

    return CommandResult(
        handled=True,
        responses=[f"Unknown command {verb!r}. Type HELP for the command list."],
    )


def _parse_pass_reject(
    verb: str, args: list[str], state: FilterState, h: CommandHandlers
) -> CommandResult:
    if not args:
        return CommandResult(handled=True, responses=[f"{verb}: missing category."])
    token = args[0].upper()
    rest = args[1:]

    if token == "MINSNR":
        return _parse_minsnr(verb, rest, state)

    if token.lower() in SWITCH_NAMES:
        on = verb == "PASS"
        state.set_switch(token.lower(), on)
        return CommandResult(
            handled=True, changed=True, responses=[f"{token} {'on' if on else 'off'}."]
        )

    if token == "NEARBY":
        # PASS enables NEARBY, REJECT disables it. A numeric argument sets the
        # radius in km; a second number sets the low-band radius.
        on = verb == "PASS"
        radius: float | None = None
        low_radius: float | None = None
        if rest:
            value = rest[0].upper()
            if value in ("OFF", "NO", "0", "FALSE"):
                on = False
            elif value in ("ON", "YES", "1", "TRUE"):
                on = True
            else:
                try:
                    radius = float(rest[0])
                except ValueError:
                    return CommandResult(
                        handled=True, responses=["NEARBY: ON|OFF|<km> [<low_km>]."]
                    )
                if radius <= 0:
                    return CommandResult(handled=True, responses=["NEARBY radius must be > 0."])
                on = True
                if len(rest) > 1:
                    try:
                        low_radius = float(rest[1])
                    except ValueError:
                        return CommandResult(
                            handled=True, responses=["NEARBY low-band radius must be a number."]
                        )
                    if low_radius <= 0:
                        return CommandResult(
                            handled=True, responses=["NEARBY radius must be > 0."]
                        )
        if h.nearby_setter is None:
            return CommandResult(handled=True, responses=["NEARBY is not available."])
        return CommandResult(
            handled=True, changed=True, responses=[h.nearby_setter(on, radius, low_radius)]
        )

    category = _CATEGORY_ALIASES.get(token)
    if category is None:
        return CommandResult(
            handled=True,
            responses=[f"{verb}: unknown filter category {token!r}. Type HELP PASS."],
        )

    raw = _split_grouped(rest) if category in _GROUPED_CATEGORIES else _split_values(rest)
    values = _normalize_values(category, raw)
    if not values:
        return CommandResult(handled=True, responses=[f"{verb} {token}: missing values."])

    if verb == "PASS":
        state.add_allow(category, values)
    else:
        state.add_reject(category, values)
    response = f"{verb} {token} {','.join(values)}."
    if (
        verb == "PASS"
        and category in EXACT_CATEGORIES
        and state.allow.get(category) is None
        and not any(v.lower() == "all" for v in values)
    ):
        # Exact categories start unrestricted, so a lone PASS adds nothing.
        # The command is accepted but has no effect until the category is
        # narrowed with REJECT <CATEGORY> ALL.
        response += (
            f" {token} is unrestricted; use REJECT {token} ALL first to show only these."
        )
    return CommandResult(handled=True, changed=True, responses=[response])


def _parse_reset(
    args: list[str], state: FilterState, h: CommandHandlers
) -> CommandResult:
    token = args[0].upper() if args else "ALL"

    if token == "ALL":
        if h.default_state_provider is not None:
            dst = h.default_state_provider()
            state.allow = {k: (set(v) if v is not None else None) for k, v in dst.allow.items()}
            state.reject = {k: set(v) for k, v in dst.reject.items()}
            state.allow_patterns = {
                k: (list(v) if v is not None else None) for k, v in dst.allow_patterns.items()
            }
            state.reject_patterns = {k: list(v) for k, v in dst.reject_patterns.items()}
            state.comment_allow = list(dst.comment_allow)
            state.comment_reject = list(dst.comment_reject)
            state.min_snr = dict(dst.min_snr)
            state.switches = dict(dst.switches)
            if h.nearby_setter is not None:
                h.nearby_setter(False, None, None)
            return CommandResult(
                handled=True, changed=True, responses=["Filter reset to node defaults."]
            )
        for cat in ALL_CATEGORIES:
            state.clear_category(cat)
        state.min_snr.clear()
        state.switches = dict(DEFAULT_SWITCHES)
        if h.nearby_setter is not None:
            h.nearby_setter(False, None, None)
        return CommandResult(handled=True, changed=True, responses=["Filter reset."])

    if token == "MINSNR":
        state.min_snr.clear()
        return CommandResult(handled=True, changed=True, responses=["MINSNR reset."])
    if token == "NEARBY":
        if h.nearby_setter is not None:
            h.nearby_setter(False, None, None)
        return CommandResult(handled=True, changed=True, responses=["NEARBY off."])
    if token in ("SWITCH", "SWITCHES"):
        state.switches = dict(DEFAULT_SWITCHES)
        return CommandResult(handled=True, changed=True, responses=["Switches reset."])

    category = _CATEGORY_ALIASES.get(token)
    if category is None:
        return CommandResult(
            handled=True, responses=[f"RESET: unknown category {token!r}. Type HELP RESET."]
        )
    state.clear_category(category)
    return CommandResult(handled=True, changed=True, responses=[f"RESET {token}."])


def _parse_minsnr(verb: str, args: list[str], state: FilterState) -> CommandResult:
    if not args:
        return CommandResult(
            handled=True, responses=["Usage: PASS MINSNR <MODE> <dB|ALL>"]
        )
    modes = [m.upper() for m in _split_values([args[0]])]
    # REJECT clears the threshold; an explicit ALL/NONE on PASS does the same.
    if verb == "REJECT":
        for mode in modes:
            state.set_min_snr(mode, None)
        return CommandResult(
            handled=True, changed=True, responses=[f"MINSNR {','.join(modes)} cleared."]
        )
    if len(args) < 2:
        return CommandResult(
            handled=True, responses=["Usage: PASS MINSNR <MODE> <dB|ALL>"]
        )
    threshold_token = args[1].upper()
    if threshold_token in ("ALL", "NONE"):
        for mode in modes:
            state.set_min_snr(mode, None)
        return CommandResult(handled=True, changed=True, responses=["MINSNR cleared."])
    try:
        threshold = int(threshold_token)
    except ValueError:
        return CommandResult(handled=True, responses=["MINSNR threshold must be an integer."])
    for mode in modes:
        state.set_min_snr(mode, threshold)
    return CommandResult(
        handled=True,
        changed=True,
        responses=[f"MINSNR {','.join(modes)} = {threshold} dB."],
    )


def _parse_set(args: list[str], state: FilterState, h: CommandHandlers) -> CommandResult:
    if not args:
        return CommandResult(handled=True, responses=["SET: missing subcommand."])
    sub = args[0].upper()
    rest = args[1:]

    if sub == "GRID":
        if not rest:
            return CommandResult(
                handled=True, responses=[f"Grid: {h.operator_grid or 'not set'}"]
            )
        grid = rest[0].upper()
        if not is_valid_grid(grid):
            return CommandResult(
                handled=True,
                responses=["Invalid Maidenhead locator; example JO90AA."],
            )
        if h.grid_setter is not None:
            h.grid_setter(grid)
        return CommandResult(
            handled=True,
            changed=True,
            responses=[f"Grid set to {grid} (NEARBY and saved preferences)."],
        )

    if sub == "NOISE":
        if not rest:
            return CommandResult(
                handled=True,
                responses=["NOISE: QUIET|RURAL|SUBURBAN|URBAN|INDUSTRIAL"],
            )
        cls = rest[0].upper()
        if h.noise_setter is not None:
            h.noise_setter(cls)
        return CommandResult(
            handled=True, changed=True, responses=[f"Noise class set to {cls}."]
        )

    if sub == "DEDUPE":
        if not rest:
            policy = h.dedupe_provider() if h.dedupe_provider is not None else "SLOW"
            return CommandResult(handled=True, responses=[f"Dedupe policy: {policy}"])
        policy = rest[0].upper()
        if policy not in _DEDUPE_POLICIES:
            return CommandResult(
                handled=True, responses=["DEDUPE: choose FAST, MED or SLOW."]
            )
        if h.dedupe_setter is not None:
            h.dedupe_setter(policy)
        return CommandResult(
            handled=True, changed=True, responses=[f"Dedupe policy set to {policy}."]
        )

    if sub in ("FT8",):
        state.add_allow("mode", [Mode.FT8.value])
        return CommandResult(handled=True, changed=True, responses=["FT8 enabled."])
    if sub in ("NOFT8",):
        state.add_reject("mode", [Mode.FT8.value])
        return CommandResult(handled=True, changed=True, responses=["FT8 disabled."])
    if sub in ("SKIMMER",):
        arg = rest[0].upper() if rest else "ON"
        if arg in ("OFF", "NO", "0"):
            state.add_reject("source", ["skimmer"])
            msg = "Skimmer spots disabled."
        else:
            state.add_allow("source", ["skimmer"])
            msg = "Skimmer spots enabled."
        return CommandResult(handled=True, changed=True, responses=[msg])
    if sub in ("DX",):
        # "SET/DX" (CC) enables spots; "SET DX FILTER ..." is acknowledged.
        if rest and rest[0].upper() == "FILTER":
            return CommandResult(handled=True, responses=["Filter accepted."])
        state.add_allow("source", ["human", "skimmer"])
        return CommandResult(handled=True, changed=True, responses=["Spots enabled."])
    if sub in ("DX_FILTER", "FILTER"):
        return CommandResult(handled=True, responses=["Filter accepted."])

    conti = _CONTI_SET_SUBS.get(sub)
    if conti is not None:
        category, negate = conti
        if negate:
            state.add_reject(category, ["all"])
            return CommandResult(
                handled=True, changed=True, responses=[f"REJECT {sub[2:]} ALL."]
            )
        # Reuse the PASS path so the "unrestricted" hint applies here too.
        return _parse_pass_reject("PASS", [sub, *rest], state, h)

    return CommandResult(handled=True, responses=[f"SET {sub}: acknowledged."])


def _parse_dx_query(args: list[str], band_names: frozenset[str]) -> DxQuery:
    """Parse ``SH/DX [<n>] [<call|prefix>] [<band>] [<mode>]`` argument order-free."""
    query = DxQuery()
    for token in args:
        if token.isdigit():
            query.count = int(token)
            continue
        band = _normalize_band(token)
        if band in band_names:
            query.band = band
            continue
        mode = _SHOW_MODE_TOKENS.get(token.upper())
        if mode is not None:
            query.mode = mode
            continue
        if not query.dx_call:
            query.dx_call = token.upper()
    return query


def _parse_show(args: list[str], state: FilterState, h: CommandHandlers) -> CommandResult:
    sub = args[0].upper() if args else "DX"
    rest = args[1:]

    if sub == "FILTER":
        category: str | None = None
        full = False
        if rest:
            token = rest[0].upper()
            if token == "FULL":
                full = True
            elif token == "NEARBY":
                if h.nearby_provider is not None:
                    return CommandResult(
                        handled=True, responses=h.nearby_provider(), pause_seconds=30.0
                    )
                return CommandResult(handled=True, responses=["NEARBY is not available."])
            elif token in ("CONF",):
                category = "confidence"
            elif token in _CATEGORY_ALIASES:
                category = _CATEGORY_ALIASES[token]
            elif token in ("MINSNR", "COMMENT", "SWITCHES"):
                category = token.lower()
        return CommandResult(
            handled=True, responses=[describe(state, category, full)], pause_seconds=30.0
        )

    if sub == "NEARBY":
        if h.nearby_provider is not None:
            return CommandResult(
                handled=True, responses=h.nearby_provider(), pause_seconds=30.0
            )
        return CommandResult(handled=True, responses=["NEARBY is not available."])

    if sub == "SETTINGS":
        return CommandResult(
            handled=True, responses=[describe(state, full=True)], pause_seconds=30.0
        )

    if sub in ("DX", "MYDX"):
        query = _parse_dx_query(rest, h.band_names)
        responses: list[str] | None = None
        if h.dx_provider is not None:
            responses = h.dx_provider(query)
        elif query.dx_call and h.recent_for_provider is not None:
            responses = h.recent_for_provider(query.dx_call, query.count)
        elif h.recent_provider is not None:
            responses = h.recent_provider(query.count)
        if not responses:
            return CommandResult(handled=True, responses=["No spots available."])
        return CommandResult(handled=True, responses=responses)

    if sub == "DEDUPE":
        policy = h.dedupe_provider() if h.dedupe_provider is not None else "SLOW"
        return CommandResult(handled=True, responses=[f"Dedupe: {policy}"])

    if sub == "HOLD":
        if h.hold_provider is not None:
            return CommandResult(handled=True, responses=[h.hold_provider()])
        return CommandResult(handled=True, responses=["Live spots are running."])

    if sub == "PROP":
        if not rest:
            return CommandResult(
                handled=True, responses=["Usage: SHOW PROP <call|prefix|grid> [band] [mode]"]
            )
        target = rest[0]
        band = rest[1] if len(rest) > 1 else ""
        mode = rest[2] if len(rest) > 2 else ""
        if h.prop_provider is not None:
            return CommandResult(
                handled=True, responses=h.prop_provider(target, band, mode), pause_seconds=30.0
            )
        return CommandResult(handled=True, responses=["Propagation outlook unavailable."])

    return CommandResult(handled=True, responses=[f"SHOW {sub}: acknowledged."])


def _parse_dx(args: list[str], h: CommandHandlers) -> CommandResult:
    if len(args) < 2:
        return CommandResult(
            handled=True, responses=["Usage: DX <freq_khz> <callsign> [comment]"]
        )
    try:
        freq = float(args[0])
    except ValueError:
        return CommandResult(handled=True, responses=["DX: frequency must be a number in kHz."])
    if not 1.0 <= freq <= 60000.0:
        return CommandResult(handled=True, responses=["DX: frequency out of range."])

    call = args[1].upper()
    if not is_valid_shape(call):
        return CommandResult(handled=True, responses=[f"DX: invalid callsign {call!r}."])

    comment = " ".join(args[2:]).strip()
    if comment and not _POST_COMMENT_RE.match(comment):
        return CommandResult(
            handled=True, responses=["DX: comment contains unsupported characters."]
        )

    request = PostRequest(freq_khz=freq, dx_call=call, comment=comment)
    if h.post_handler is not None:
        response = h.post_handler(request)
    else:
        response = "Spot posting is not available."
    return CommandResult(handled=True, responses=[response], post=request)


def _parse_pause(args: list[str], h: CommandHandlers) -> CommandResult:
    seconds = 30
    if args and args[0].isdigit():
        seconds = max(1, min(300, int(args[0])))
    if h.pause_setter is not None:
        response = h.pause_setter(seconds)
    else:
        response = f"Live spots paused for {seconds}s."
    return CommandResult(handled=True, responses=[response], pause_seconds=float(seconds))


def _parse_help(args: list[str]) -> CommandResult:
    topic = args[0].upper() if args else ""
    topics = {
        "DX": "DX <freq_khz> <callsign> [comment]  Post a spot you have heard.",
        "PASS": (
            "PASS <CATEGORY> <values>  Allow values; PASS <CATEGORY> ALL clears.\n"
            "Categories: BAND MODE SOURCE DXCALL DECALL DXCONT DECONT DXZONE DEZONE\n"
            "            DXDXCC DEDXCC DXGRID2 DEGRID2 CONFIDENCE PATH COMMENT EVENT\n"
            "Switches:   BEACON WWV WCY ANNOUNCE SELF\n"
            "Special:    PASS MINSNR <MODE> <dB|ALL> | PASS NEARBY ON|OFF|<km> [<low_km>]"
        ),
        "REJECT": (
            "REJECT <CATEGORY> <values>  Block values; REJECT <CATEGORY> ALL blocks all.\n"
            "REJECT wins over PASS within a category."
        ),
        "SHOW": (
            "SHOW DX [call|prefix] [band] [mode] [n]  (alias SH/DX)  Show recent\n"
            "spots matching your filters. SHOW FILTER [FULL|<CATEGORY>] |\n"
            "SHOW SETTINGS | SHOW DEDUPE | SHOW NEARBY | SHOW HOLD |\n"
            "SHOW PROP <call|prefix|grid> [band] [mode]"
        ),
        "SET": "SET GRID <locator> | SET NOISE <class> | SET DEDUPE <FAST|MED|SLOW>",
        "RESET": (
            "RESET [ALL|<CATEGORY>|MINSNR|NEARBY|SWITCHES]  Restore the filter.\n"
            "RESET alone restores the node-level defaults; RESET <CATEGORY> clears\n"
            "one category. CLEAR is an alias."
        ),
    }
    if topic in topics:
        return CommandResult(handled=True, responses=[topics[topic]])
    return CommandResult(handled=True, responses=[_help_text()])


def _help_text() -> str:
    return (
        "RXCluster help\n"
        "  PASS/REJECT BAND|MODE|SOURCE|DXCALL|DECALL|DXCONT|DECONT|DXZONE|DEZONE\n"
        "              DXDXCC|DEDXCC|DXGRID2|DEGRID2|CONFIDENCE|PATH|COMMENT|EVENT <values>\n"
        "  PASS/REJECT BEACON|WWV|WCY|ANNOUNCE|SELF\n"
        "  PASS MINSNR <MODE> <dB|ALL> | PASS NEARBY ON|OFF|<km> [<low_km>]\n"
        "  DX <freq_khz> <call> [comment]\n"
        "  SHOW DX [call|prefix] [band] [mode] [n] (alias SH/DX)\n"
        "  SHOW FILTER [FULL|<CAT>] | SHOW SETTINGS\n"
        "  SHOW DEDUPE | SHOW NEARBY | SHOW HOLD\n"
        "  SHOW PROP <call|prefix|grid> [band] [mode] | WHOSPOTSME [band]\n"
        "  PAUSE [seconds] | RESUME\n"
        "  SET GRID <locator> | SET NOISE <class> | SET DEDUPE <FAST|MED|SLOW>\n"
        "  SET/SKIMMER [ON|OFF] | SET/FT8 | SET/NOFT8\n"
        "  RESET [ALL|<CATEGORY>|MINSNR|NEARBY|SWITCHES] (alias CLEAR)\n"
        "  HELP [command] | BYE"
    )
