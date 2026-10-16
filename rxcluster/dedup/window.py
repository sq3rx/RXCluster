"""Time-windowed duplicate suppression.

Repeated identical reports (same spotter, call and quantized frequency) within
the configured window are collapsed so the pipeline does not forward the same
information many times. Cross-source *corroboration* is handled separately by
:mod:`rxcluster.validate.corroboration`.
"""

from __future__ import annotations

import time
from collections.abc import Hashable

from ..models import Spot


class DedupWindow:
    """Sliding-window duplicate detector."""

    def __init__(self, window_seconds: float, freq_tolerance_khz: float = 0.1) -> None:
        self.window = max(window_seconds, 0.0)
        self.freq_tolerance = max(freq_tolerance_khz, 1e-6)
        self._seen: dict[Hashable, float] = {}
        self._last_prune = time.monotonic()
        self._prune_interval = max(self.window, 5.0)

    def _key(self, spot: Spot) -> Hashable:
        call, bucket = spot.key(self.freq_tolerance)
        return (call, bucket, spot.spotter.upper())

    def is_duplicate(self, spot: Spot, now: float | None = None) -> bool:
        """Return ``True`` if an identical spot was seen within the window."""
        now = now if now is not None else time.monotonic()
        key = self._key(spot)
        last = self._seen.get(key)
        if last is not None and (now - last) < self.window:
            self._seen[key] = now
            return True
        self._seen[key] = now
        self._prune(now)
        return False

    def _prune(self, now: float) -> None:
        if now - self._last_prune < self._prune_interval:
            return
        self._last_prune = now
        cutoff = now - self.window
        stale = [k for k, ts in self._seen.items() if ts < cutoff]
        for key in stale:
            del self._seen[key]

    def __len__(self) -> int:
        return len(self._seen)