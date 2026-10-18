"""Core data model for RXCluster.

The central object is :class:`Spot`: a normalized, enriched DX spot flowing
through the pipeline. All source-specific parsing produces a ``Spot`` and all
downstream stages (dedup, validation, enrichment, filtering, output) operate on
it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Source(StrEnum):
    """Where a spot originated."""

    RBN = "RBN"
    DXSUMMIT = "DXSUMMIT"
    VE7CC = "VE7CC"
    PSKREPORTER = "PSKREPORTER"
    MANUAL = "MANUAL"


class SourceType(StrEnum):
    """Whether a spot came from an automated skimmer or a human operator."""

    HUMAN = "HUMAN"
    SKIMMER = "SKIMMER"


class Mode(StrEnum):
    """Operating mode. ``UNKNOWN`` is used when it cannot be inferred."""

    CW = "CW"
    SSB = "SSB"
    RTTY = "RTTY"
    FT8 = "FT8"
    FT4 = "FT4"
    PSK = "PSK"
    UNKNOWN = "UNKNOWN"


class SpotKind(StrEnum):
    """Message class carried through the pipeline.

    Ordinary spots are ``SPOT``; the remaining kinds are informational traffic
    controlled by the corresponding feature switches (``BEACON``, ``WWV``,
    ``WCY``, ``ANNOUNCE``).
    """

    SPOT = "SPOT"
    BEACON = "BEACON"
    WWV = "WWV"
    WCY = "WCY"
    ANNOUNCE = "ANNOUNCE"


class Confidence(StrEnum):
    """N2WQ/GoCluster-style callsign confidence symbols."""

    LOW = "?"        # little supporting evidence
    STATIC = "S"     # single report with static/recent on-band support
    PARTIAL = "P"    # corroborated below the strongest level
    VALID = "V"      # strongly corroborated
    CORRECTED = "C"  # original call corrected and validated
    BUST = "B"       # suggested correction failed validation


class PathClass(StrEnum):
    """Propagation path reliability classes (rendered as path symbols)."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNLIKELY = "UNLIKELY"
    CLOSED = "CLOSED"
    INSUFFICIENT = "INSUFFICIENT"


# Rendering of path classes to the single-character N2WQ symbols.
PATH_SYMBOL: dict[PathClass, str] = {
    PathClass.HIGH: ">",
    PathClass.MEDIUM: "=",
    PathClass.LOW: "<",
    PathClass.UNLIKELY: "-",
    PathClass.CLOSED: "#",
    PathClass.INSUFFICIENT: " ",
}


@dataclass(slots=True)
class Spot:
    """A normalized DX spot."""

    # --- Identity / origin -------------------------------------------------
    source: Source
    source_type: SourceType
    spotter: str
    dx_call: str
    freq_khz: float
    timestamp: float  # UNIX epoch seconds (UTC)

    # --- Parsed payload ----------------------------------------------------
    comment: str = ""
    mode: Mode = Mode.UNKNOWN
    band: str = ""
    snr: int | None = None
    speed_wpm: int | None = None

    # --- Derived / enriched ------------------------------------------------
    spotter_grid: str = ""
    dx_grid: str = ""
    dxcc: str = ""
    continent: str = ""
    cq_zone: int | None = None
    # Geography of the spotting station (resolved via cty.dat).
    spotter_dxcc: str = ""
    spotter_continent: str = ""
    spotter_cq_zone: int | None = None
    confidence: Confidence = Confidence.LOW
    path: PathClass = PathClass.INSUFFICIENT

    # --- Internal bookkeeping ---------------------------------------------
    is_beacon: bool = False
    kind: SpotKind = SpotKind.SPOT

    def key(self, freq_tolerance_khz: float = 0.1) -> tuple[str, int]:
        """Return a dedup key: normalized callsign + quantized frequency.

        The frequency is quantized by ``freq_tolerance_khz`` so that the same
        report from slightly mis-calibrated receivers collapses to one key.
        """
        bucket = int(round(self.freq_khz / max(freq_tolerance_khz, 1e-6)))
        return self.dx_call.upper(), bucket


@dataclass(slots=True)
class SpotStats:
    """Running counters exposed via metrics/health."""

    received: int = 0
    parsed: int = 0
    parse_errors: int = 0
    deduped: int = 0
    rejected: int = 0
    forwarded: int = 0
    by_source: dict[str, int] = field(default_factory=dict)

    def bump_source(self, source: Source) -> None:
        self.by_source[source.value] = self.by_source.get(source.value, 0) + 1