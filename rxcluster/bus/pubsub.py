"""In-process publish/subscribe fan-out with per-subscriber backpressure.

The pipeline produces one enriched spot; :class:`SpotBus` distributes the
rendered line to every subscriber whose compiled filter accepts the spot. Each
subscriber owns a bounded queue. When a subscriber is too slow the *oldest*
queued line is dropped (drop-oldest) so that a slow client can never introduce
latency for the rest of the system.
"""

from __future__ import annotations

import asyncio
import logging

from ..filters.compiled import CompiledFilter
from ..models import Spot

log = logging.getLogger(__name__)


class Subscriber:
    """A connected consumer (telnet client, web socket, ...)."""

    __slots__ = ("name", "filter", "queue", "dropped")

    def __init__(self, name: str, compiled_filter: CompiledFilter, queue_size: int = 5000) -> None:
        self.name = name
        self.filter = compiled_filter
        self.queue: asyncio.Queue[str] = asyncio.Queue(maxsize=max(queue_size, 1))
        self.dropped = 0

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

    def publish(self, spot: Spot, line: str) -> int:
        """Deliver ``line`` to all matching subscribers. Returns delivery count."""
        delivered = 0
        # Iterate over a snapshot: subscribers may disconnect while publishing.
        for sub in tuple(self._subscribers):
            if sub.filter is None or sub.filter.allows(spot):
                if sub.offer(line):
                    delivered += 1
        return delivered