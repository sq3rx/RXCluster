"""Base class for source connectors.

Each connector runs as an asyncio task, maintains its connection with
exponential-backoff reconnection and emits normalized spots through an async
``emit`` callback (usually the pipeline's intake queue).
"""

from __future__ import annotations

import abc
import asyncio
import logging
from collections.abc import Awaitable, Callable

from ..models import Spot

log = logging.getLogger(__name__)

EmitFn = Callable[[Spot], Awaitable[None]]


class SourceConnector(abc.ABC):
    name: str = "source"

    def __init__(
        self,
        emit: EmitFn,
        reconnect_delay: float = 5.0,
        max_reconnect_delay: float = 120.0,
    ) -> None:
        self.emit = emit
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_delay = max_reconnect_delay

    @abc.abstractmethod
    async def _stream_once(self) -> None:
        """Run one connection session. Return when the stream ends."""

    async def run(self) -> None:
        delay = self.reconnect_delay
        while True:
            try:
                await self._stream_once()
                delay = self.reconnect_delay
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - network dependent
                log.warning("[%s] connection error: %s", self.name, exc)
                delay = min(max(delay * 2, self.reconnect_delay), self.max_reconnect_delay)
            else:
                log.info("[%s] stream ended; reconnecting in %.0fs", self.name, delay)
            await asyncio.sleep(delay)