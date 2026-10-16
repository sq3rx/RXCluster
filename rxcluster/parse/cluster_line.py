"""Parsing of raw DX cluster / RBN lines into :class:`~rxcluster.models.Spot`."""

from __future__ import annotations

import re
import time

from ..models import Mode, Source, SourceType, Spot, SpotKind

# Standard DX cluster / RBN spot line:
#   DX de W3LPL-#:     7003.0  K1ABC            CW    12 dB  28 WPM  CQ      1234Z
LINE_RE = re.compile(
    r"^DX\s+de\s+(?P<spotter>[A-Z0-9/\-#]+)\s*:\s+"
    r"(?P<freq>\d+(?:\.\d+)?)\s+"
    r"(?P<dx>[A-Z0-9][A-Z0-9/\-]*[A-Z0-9]|[A-Z0-9])\s+"
    r"(?P<rest>.*?)\s*"
    r"(?P<time>\d{4})Z\s*$",
    re.IGNORECASE,
)

SNR_RE = re.compile(r"(?<!\d)(?P<snr>-?\d{1,2})\s*dB\b", re.IGNORECASE)
WPM_RE = re.compile(r"(?<!\d)(?P<wpm>\d{2,3})\s*WPM\b", re.IGNORECASE)

# Whole-token mode keywords, checked in priority order.
_MODE_TOKENS: list[tuple[re.Pattern[str], Mode]] = [
    (re.compile(r"\bFT8\b", re.IGNORECASE), Mode.FT8),
    (re.compile(r"\bFT4\b", re.IGNORECASE), Mode.FT4),
    (re.compile(r"\bRTTY\b", re.IGNORECASE), Mode.RTTY),
    (re.compile(r"\bPSK(?:31|63|125)?\b", re.IGNORECASE), Mode.PSK),
    (re.compile(r"\bCW\b", re.IGNORECASE), Mode.CW),
    (re.compile(r"\b(?:SSB|USB|LSB|PHONE)\b", re.IGNORECASE), Mode.SSB),
]

BEACON_RE = re.compile(r"\b(?:BCN|BEACON|NCDXF|/B)\b", re.IGNORECASE)

# WWV/WCY propagation bulletins and ANNOUNCE messages from CC Cluster nodes:
#   WWV de W3LPL: SFI=145 A=8 K=2 ...
#   WCY de W3LPL: ...
#   ANN de W3LPL: contest starts at 0000Z
_BULLETIN_RE = re.compile(
    r"^(?P<kind>WWV|WCY|ANNOUNCE|ANN)\s+de\s+(?P<spotter>[A-Z0-9/\-#]+)\s*:\s*(?P<text>.*)$",
    re.IGNORECASE,
)
_BULLETIN_KINDS: dict[str, SpotKind] = {
    "WWV": SpotKind.WWV,
    "WCY": SpotKind.WCY,
    "ANN": SpotKind.ANNOUNCE,
    "ANNOUNCE": SpotKind.ANNOUNCE,
}


def parse_bulletin(line: str, source: Source) -> Spot | None:
    """Parse a WWV/WCY/ANNOUNCE bulletin line. Returns ``None`` if it does not match."""
    match = _BULLETIN_RE.match(line.strip())
    if match is None:
        return None
    return Spot(
        source=source,
        source_type=SourceType.HUMAN,
        spotter=match.group("spotter").upper(),
        dx_call="",
        freq_khz=0.0,
        timestamp=time.time(),
        comment=match.group("text").strip(),
        kind=_BULLETIN_KINDS[match.group("kind").upper()],
    )


def mode_from_text(text: str) -> Mode | None:
    """Extract an explicit mode keyword from a comment string."""
    for pattern, mode in _MODE_TOKENS:
        if pattern.search(text):
            return mode
    return None


def is_beacon(comment: str, dx_call: str) -> bool:
    return bool(BEACON_RE.search(comment) or dx_call.upper().endswith("/B"))


def parse_comment(rest: str) -> tuple[Mode | None, int | None, int | None, str]:
    """Split a comment field into ``(mode, snr, wpm, cleaned_comment)``.

    RBN comments look like ``CW    25 dB  28 WPM  CQ``; human comments are
    arbitrary free text. Tokens that are recognized as metadata are removed
    from the returned comment.
    """
    mode: Mode | None = None
    snr: int | None = None
    wpm: int | None = None

    snr_match = SNR_RE.search(rest)
    if snr_match:
        snr = int(snr_match.group("snr"))
    wpm_match = WPM_RE.search(rest)
    if wpm_match:
        wpm = int(wpm_match.group("wpm"))

    mode = mode_from_text(rest)

    cleaned = rest
    if snr_match:
        cleaned = cleaned.replace(snr_match.group(0), " ")
    if wpm_match:
        cleaned = cleaned.replace(wpm_match.group(0), " ")
    # Drop a leading standalone mode token once it has been captured.
    if mode is not None:
        cleaned = _MODE_TOKENS_MAP[mode].sub(" ", cleaned, count=1)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return mode, snr, wpm, cleaned


_MODE_TOKENS_MAP: dict[Mode, re.Pattern[str]] = {m: p for p, m in _MODE_TOKENS}


def parse_cluster_line(
    line: str,
    source: Source,
    source_type: SourceType = SourceType.SKIMMER,
) -> Spot | None:
    """Parse a single ``DX de ...`` line. Returns ``None`` if it does not match."""
    match = LINE_RE.match(line.strip())
    if match is None:
        return None

    spotter = match.group("spotter").upper()
    dx_call = match.group("dx").upper()
    freq = float(match.group("freq"))
    rest = match.group("rest").strip()

    mode, snr, wpm, comment = parse_comment(rest)

    # Spotters ending in "-" (e.g. "K3LR-") or "-NN" are skimmers on the RBN.
    if source is Source.RBN or spotter.endswith("-") or "-#" in spotter:
        source_type = SourceType.SKIMMER

    beacon = is_beacon(comment, dx_call)
    return Spot(
        source=source,
        source_type=source_type,
        spotter=spotter.rstrip("#-"),
        dx_call=dx_call,
        freq_khz=freq,
        timestamp=time.time(),
        comment=comment,
        mode=mode or Mode.UNKNOWN,
        snr=snr,
        speed_wpm=wpm,
        is_beacon=beacon,
        kind=SpotKind.BEACON if beacon else SpotKind.SPOT,
    )