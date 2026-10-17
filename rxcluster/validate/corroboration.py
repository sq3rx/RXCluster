"""Cross-source corroboration and busted-call detection.

Observations of the same callsign on (approximately) the same frequency from
several independent receivers/operators raise confidence. A lone report that
does not appear in the SCP and has a close neighbor with strong support is
flagged as a busted spot, together with the suggested correction. The validator
turns that suggestion into a ``C`` (corrected) or ``B`` (busted) tag.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..models import Confidence, Spot
from .patterns import base_call


def levenshtein(a: str, b: str, max_distance: int = 2) -> int:
    """Bounded Levenshtein distance (returns ``max_distance`` + 1 when exceeded)."""
    if abs(len(a) - len(b)) > max_distance:
        return max_distance + 1
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i] + [0] * len(b)
        best = cur[0]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if cur[j] < best:
                best = cur[j]
        if best > max_distance:
            return max_distance + 1
        prev = cur
    return prev[-1]


@dataclass(slots=True)
class _Observation:
    call: str
    spotter: str
    ts: float


@dataclass
class CorroborationResult:
    confidence: Confidence
    suggested_call: str = ""
    distinct_spotters: int = 0


@dataclass
class Corroborator:
    """Tracks recent observations per frequency bucket."""

    window_seconds: float = 120.0
    min_agree: int = 3
    edit_distance: int = 1
    freq_tolerance_khz: float = 0.1
    _by_freq: dict[int, list[_Observation]] = field(default_factory=dict)
    _last_prune: float = 0.0

    def _bucket(self, freq_khz: float) -> int:
        return int(round(freq_khz / max(self.freq_tolerance_khz, 1e-6)))

    def _prune(self, bucket: int, now: float) -> list[_Observation]:
        records = self._by_freq.get(bucket, [])
        cutoff = now - self.window_seconds
        records = [r for r in records if r.ts >= cutoff]
        if records:
            self._by_freq[bucket] = records
        else:
            self._by_freq.pop(bucket, None)
        return records

    def _sweep(self, now: float) -> None:
        """Drop observations from every bucket, not just the current one.

        Without this, buckets that stop seeing traffic would never be pruned
        and ``_by_freq`` would grow without bound.
        """
        interval = max(self.window_seconds, 5.0)
        if now - self._last_prune < interval:
            return
        self._last_prune = now
        cutoff = now - self.window_seconds
        for bucket in list(self._by_freq):
            records = [r for r in self._by_freq[bucket] if r.ts >= cutoff]
            if records:
                self._by_freq[bucket] = records
            else:
                del self._by_freq[bucket]

    def evaluate(
        self, spot: Spot, in_scp: bool | None = None, now: float | None = None
    ) -> CorroborationResult:
        now = time.monotonic() if now is None else now
        bucket = self._bucket(spot.freq_khz)
        records = self._prune(bucket, now)

        call = base_call(spot.dx_call)
        spotters = {r.spotter for r in records if r.call == call}
        spotters.add(spot.spotter.upper())
        n = len(spotters)

        records.append(_Observation(call=call, spotter=spot.spotter.upper(), ts=now))
        self._by_freq[bucket] = records
        self._sweep(now)

        if n >= self.min_agree:
            return CorroborationResult(Confidence.VALID, distinct_spotters=n)
        if n >= 2:
            return CorroborationResult(Confidence.PARTIAL, distinct_spotters=n)

        # Single observation. Only attempt bust detection when the call is not
        # a known-good SCP callsign.
        if in_scp is not True and self.edit_distance > 0:
            suggestion = self._find_correction(call, records, now)
            if suggestion is not None:
                return CorroborationResult(
                    Confidence.BUST, suggested_call=suggestion, distinct_spotters=n
                )

        return CorroborationResult(
            Confidence.STATIC if in_scp else Confidence.LOW, distinct_spotters=n
        )

    def _find_correction(self, call: str, records: list[_Observation], now: float) -> str | None:
        support: dict[str, set[str]] = {}
        for r in records:
            if r.call == call:
                continue
            support.setdefault(r.call, set()).add(r.spotter)
        best: str | None = None
        best_support = 1
        for other, spotters in support.items():
            if len(spotters) < 2:
                continue
            if levenshtein(call, other, self.edit_distance) <= self.edit_distance:
                if len(spotters) > best_support:
                    best_support = len(spotters)
                    best = other
        return best