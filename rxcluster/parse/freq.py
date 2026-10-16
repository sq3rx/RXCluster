"""Band and mode determination from frequency.

The :class:`BandPlan` is built once from the parsed configuration and provides
fast lookups used on the hot path:

* :meth:`band_for_freq` - map a frequency (kHz) to a band name via ``bisect``.
* :meth:`infer_mode` - infer the operating mode for human spots that carry no
  explicit mode token, using configurable sub-band splits.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass

from ..models import Mode


@dataclass(slots=True, frozen=True)
class _Range:
    low: float
    high: float
    name: str


class BandPlan:
    """Frequency -> band and mode resolution."""

    def __init__(
        self,
        band_ranges: list[tuple[float, float, str]],
        mode_subbands: dict[str, dict[str, float]] | None = None,
    ) -> None:
        self._ranges = sorted(
            (_Range(low, high, name) for low, high, name in band_ranges),
            key=lambda r: r.low,
        )
        # Precompute boundary list for bisect: the end of each band.
        self._endpoints = [r.high for r in self._ranges]
        self._subbands = mode_subbands or {}

    def band_for_freq(self, freq_khz: float) -> str:
        """Return the band name or ``""`` if the frequency is outside any band."""
        # Find the first band whose high >= freq, then verify low <= freq.
        idx = bisect_right(self._endpoints, freq_khz)
        if idx < len(self._ranges):
            rng = self._ranges[idx]
            if rng.low <= freq_khz <= rng.high:
                return rng.name
        return ""

    def infer_mode(self, freq_khz: float, band: str, explicit: Mode | None = None) -> Mode:
        """Return ``explicit`` when provided, else infer from the sub-band plan."""
        if explicit is not None and explicit is not Mode.UNKNOWN:
            return explicit
        split = self._subbands.get(band)
        if not split:
            return Mode.UNKNOWN
        cw_high = split.get("cw_high")
        ssb_low = split.get("ssb_low")
        if cw_high is not None and freq_khz <= cw_high:
            return Mode.CW
        if ssb_low is not None and freq_khz >= ssb_low:
            return Mode.SSB
        # Between the CW and SSB boundaries we cannot decide reliably.
        return Mode.UNKNOWN