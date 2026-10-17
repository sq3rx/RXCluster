"""In-process publish/subscribe fan-out with per-subscriber backpressure.

The pipeline produces one enriched spot; :class:`SpotBus` distributes the
rendered line to every subscriber whose compiled filter accepts the spot. Each
subscriber owns a bounded queue. When a subscriber is too slow the *oldest*
queued line is dropped (drop-oldest) so that a slow client can never introduce
latency for the rest of the system.

Each subscriber also runs its own duplicate-suppression window, applied after
that subscriber's filter, so the ``SET DEDUPE`` policy can differ per client.
"""

from __future__ import annotations

import asyncio
import logging

from ..dedup.window import DedupWindow
from ..filters.compiled import CompiledFilter
from ..models import Spot

log = logging.getLogger(__name__)


class Subscriber:
    """A connected consumer (telnet client, web socket, ...)."""

    __slots__ = ("name", "filter", "queue", "dropped", "_dedup", "_freq_tolerance")

    def __init__(
        self,
        name: str,
        compiled_filter: CompiledFilter,
        queue_size: int = 5000,
        dedup_window_seconds: float = 0.0,
        freq_tolerance_khz: float = 0.1,
    ) -> None:
        self.name = name
        self.filter = compiled_filter
        self.queue: asyncio.Queue[str] = asyncio.Queue(maxsize=max(queue_size, 1))
        self.dropped = 0
        self._freq_tolerance = max(freq_tolerance_khz, 1e-6)
        self._dedup = self._make_dedup(dedup_window_seconds)

    def _make_dedup(self, window_seconds: float) -> DedupWindow | None:
        if window_seconds <= 0:
            return None
        return DedupWindow(window_seconds, self._freq_tolerance)

    def set_dedup_window(
        self, window_seconds: float, freq_tolerance_khz: float | None = None
    ) -> None:
        """(Re)configure this subscriber's dedup window, e.g. on SET DEDUPE."""
        if freq_tolerance_khz is not None:
            self._freq_tolerance = max(freq_tolerance_khz, 1e-6)
        self._dedup = self._make_dedup(window_seconds)

    @property
    def dedup_window_seconds(self) -> float:
        """Current duplicate-suppression window in seconds (0 = disabled)."""
        return self._dedup.window if self._dedup is not None else 0.0

    def is_duplicate(self, spot: Spot) -> bool:
        """Return whether ``spot`` duplicates one already sent to this client."""
        if self._dedup is None:
            return False
        return self._dedup.is_duplicate(spot)

    def offer(self, line: str) -> bool:
        """Enqueue a line, dropping the oldest entry if the queue is full."""
        try:
            self.queue.put_nowait(line)
            return True
        except asyncio.QueueFull:
            try:
                self.queue.get_nowait()
                self.dropped += 1
            except asyncio.QueueEmpty:
                pass
            try:
                self.queue.put_nowait(line)
            except asyncio.QueueFull:
                self.dropped += 1
                return False
            return True

    async def get(self) -> str:
        return await self.queue.get()


class SpotBus:
    def __init__(self) -> None:
        self._subscribers: set[Subscriber] = set()

    def subscribe(self, subscriber: Subscriber) -> None:
        self._subscribers.add(subscriber)

    def unsubscribe(self, subscriber: Subscriber) -> None:
        self._subscribers.discard(subscriber)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def publish(self, spot: Spot, line: str) -> tuple[int, int]:
        """Deliver ``line`` to matching subscribers.

        Returns ``(delivered, suppressed)``: the number of subscribers that
        accepted the line, and the number that dropped it as a duplicate.
        """
        delivered = 0
        suppressed = 0
        # Iterate over a snapshot: subscribers may disconnect while publishing.
        for sub in tuple(self._subscribers):
            if sub.filter is not None and not sub.filter.allows(spot):
                continue
            if sub.is_duplicate(spot):
                suppressed += 1
                continue
            if sub.offer(line):
                delivered += 1
        return delivered, suppressed
