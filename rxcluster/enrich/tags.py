"""Enriched output formatting.

Renders a :class:`~rxcluster.models.Spot` as a fixed-width, N2WQ/GoCluster
compatible DX cluster line. The layout mirrors GoCluster's ``spot.FormatDXCluster``
so that N1MM Logger+ can read the propagation glyph and the callsign confidence
tag from stable columns::

    DX de W1ABC:     14074.00  K1XYZ       FT8 -12 dB             > FN31 V 1830Z

The line has a fixed width (76 characters by default, excluding CRLF). The
1-based columns are:

* ``1-6``    ``"DX de "``
* ``7-..``   spotter callsign with ``":"`` suffix, padded so the frequency ends
  at column 25
* ``..25``   frequency, right-aligned, two decimals (``14074.00``)
* ``28-37``  DX callsign, left-aligned (padded to 8, display-truncated to 10)
* ``40-..``  mode token, signal report and free comment
* ``62``     space
* ``63``     propagation path glyph (``>``/``=``/``<``/``-``/``#`` or blank)
* ``64``     space
* ``65-68``  DX grid locator (4 characters)
* ``69``     space
* ``70``     callsign confidence symbol (``? S P C V B`` or blank)
* ``71``     space
* ``72-76``  UTC time (``HHMMZ``)

The comment is truncated so it can never push the fixed tail
(glyph/grid/confidence/time) out of position.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ..config import TagsConfig
from ..models import PATH_SYMBOL, Mode, SourceType, Spot, SpotKind

# Fixed-width layout constants, mirroring GoCluster's spot package.
DEFAULT_LINE_WIDTH = 76
MIN_LINE_WIDTH = 65
TAIL_LENGTH = 15

FREQ_END_COLUMN = 25
DX_CALL_PAD = 8
DX_CALL_MAX_DISPLAY = 10
MODE_COLUMN = 40

_MODE_TOKEN: dict[Mode, str] = {
    Mode.CW: "CW",
    Mode.RTTY: "RTTY",
    Mode.PSK: "PSK",
    Mode.FT8: "FT8",
    Mode.FT4: "FT4",
}

# SSB is rendered as USB/LSB (there is no "SSB" token). Phone convention:
# LSB below 10 MHz, USB at/above; 60 m is USB by regulation.
_SSB_USB_MIN_KHZ = 10000.0


def n2wq_mode_token(mode: Mode, freq_khz: float, band: str = "") -> str | None:
    """Return the N2WQ/GoCluster mode token for ``mode``, or ``None`` if unknown."""
    if mode is Mode.SSB:
        if band == "60m" or freq_khz >= _SSB_USB_MIN_KHZ:
            return "USB"
        return "LSB"
    return _MODE_TOKEN.get(mode)


def _format_report(mode: Mode, snr: int) -> str:
    """Format a signal report the way GoCluster does.

    CW/RTTY render as ``"25 dB"``; all other modes carry a sign for
    non-negative values (``"+25 dB"``, ``"-12 dB"``).
    """
    if mode in (Mode.CW, Mode.RTTY):
        return f"{snr} dB"
    sign = "+" if snr >= 0 else ""
    return f"{sign}{snr} dB"


def format_time(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).strftime("%H%M")


def wire_spotter(spot: Spot) -> str:
    """Return the spotter token for the wire, re-adding the RBN skimmer marker.

    Skimmer spots must keep the ``-#`` suffix so N1MM recognises them as
    skimmer reports; the stored :attr:`Spot.spotter` is always the bare
    operator callsign (without the marker).
    """
    if spot.source_type is SourceType.SKIMMER and spot.spotter:
        return f"{spot.spotter}-#"
    return spot.spotter


def _sanitize_comment(comment: str) -> str:
    """Collapse to printable ASCII so the fixed tail cannot be shifted."""
    if comment.isascii() and all(0x20 <= ord(c) <= 0x7E for c in comment):
        return " ".join(comment.split())
    out: list[str] = []
    last_space = True
    for char in comment:
        if char.isspace():
            if not last_space:
                out.append(" ")
                last_space = True
            continue
        code = ord(char)
        if code < 0x20 or code == 0x7F:
            continue
        out.append(char if code <= 0x7E else "?")
        last_space = False
    return "".join(out).strip()


def _pad_to(buffer: list[str], column: int) -> None:
    """Pad ``buffer`` so the next appended character lands at ``column`` (1-based)."""
    target = max(column - 1, 0)
    length = sum(len(part) for part in buffer)
    if length < target:
        buffer.append(" " * (target - length))


_BULLETIN_PREFIX: dict[SpotKind, str] = {
    SpotKind.WWV: "WWV",
    SpotKind.WCY: "WCY",
    SpotKind.ANNOUNCE: "ANN",
}


def render_bulletin(spot: Spot, width: int = DEFAULT_LINE_WIDTH) -> str:
    """Render a WWV/WCY/ANNOUNCE bulletin line (without line ending)."""
    prefix = _BULLETIN_PREFIX.get(spot.kind, "ANN")
    line = f"{prefix} de {spot.spotter}: {spot.comment} {format_time(spot.timestamp)}Z"
    if len(line) > width:
        line = line[:width]
    return line


def render_line(spot: Spot, cfg: TagsConfig, width: int = DEFAULT_LINE_WIDTH) -> str:
    """Render one spot to the fixed-width N2WQ/GoCluster wire format.

    The returned string is exactly ``width`` characters long (no CRLF); the
    telnet layer appends CRLF.
    """
    width = max(width, MIN_LINE_WIDTH)
    tail_start = width - TAIL_LENGTH

    freq = f"{spot.freq_khz:.2f}"
    de_call = wire_spotter(spot)

    # Trim the spotter (and, if needed, the skimmer marker) so the prefix still
    # leaves room for a gap before the right-aligned frequency.
    max_prefix_len = FREQ_END_COLUMN - len(freq)
    max_de_len = max_prefix_len - len("DX de ") - len(":")
    max_de_len = max(max_de_len, 1)
    for marker in ("-#", "-@"):
        if de_call.endswith(marker) and len(de_call) > max_de_len - 1:
            de_call = de_call[: -len(marker)]
            break
    if len(de_call) > max_de_len:
        de_call = de_call[:max_de_len]

    buffer: list[str] = [f"DX de {de_call}:"]
    _pad_to(buffer, FREQ_END_COLUMN - len(freq) + 1)
    buffer.append(freq)
    buffer.append("  ")

    length = sum(len(part) for part in buffer)
    dx_call = (spot.dx_call or "").upper()[:DX_CALL_MAX_DISPLAY]
    max_dx_len = max((MODE_COLUMN - 1) - length, 0)
    dx_call = dx_call[:max_dx_len]
    buffer.append(dx_call)
    if len(dx_call) < DX_CALL_PAD:
        buffer.append(" " * (DX_CALL_PAD - len(dx_call)))
    _pad_to(buffer, MODE_COLUMN)

    head = ""
    if cfg.mode_token:
        token = n2wq_mode_token(spot.mode, spot.freq_khz, spot.band)
        if token:
            head = token
    if spot.snr is not None:
        report = _format_report(spot.mode, spot.snr)
        head = f"{head} {report}".strip()
    buffer.append(head)
    length = sum(len(part) for part in buffer)

    comment_bits: list[str] = []
    if spot.speed_wpm is not None:
        comment_bits.append(f"{spot.speed_wpm} WPM")
    if spot.comment:
        comment_bits.append(_sanitize_comment(spot.comment))
    comment = " ".join(bit for bit in comment_bits if bit)

    if comment:
        remaining = (tail_start - 1) - length
        if head:
            if remaining <= 1:
                remaining = 0
            else:
                buffer.append(" ")
                remaining -= 1
        if remaining > 0:
            buffer.append(comment[:remaining])

    line = "".join(buffer)
    if len(line) > tail_start:
        line = line[:tail_start]
    elif len(line) < tail_start:
        line = line + " " * (tail_start - len(line))

    glyph = " "
    if cfg.path and spot.path is not None:
        glyph = PATH_SYMBOL.get(spot.path, " ")
    grid = (spot.dx_grid or "").upper()[:4].ljust(4)
    conf = spot.confidence.value if cfg.confidence else " "
    return line + f" {glyph} {grid} {conf} {format_time(spot.timestamp)}Z"
