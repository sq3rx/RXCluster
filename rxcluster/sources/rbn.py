"""Reverse Beacon Network telnet connector.

RBN relay servers stream skimmer spots in the standard ``DX de`` format and do
not respond to user commands. Login is performed with a callsign.
"""

from __future__ import annotations

import asyncio
import logging

from ..config import RbnConfig
from ..models import Source, SourceType
from ..parse.cluster_line import parse_cluster_line
from .base import SourceConnector

log = logging.getLogger(__name__)


class RbnConnector(SourceConnector):
    name = "RBN"

    def __init__(self, cfg: RbnConfig, emit) -> None:
        super().__init__(emit, cfg.reconnect_delay, cfg.max_reconnect_delay)
        self.cfg = cfg

    async def _stream_once(self) -> None:
        reader, writer = await asyncio.open_connection(self.cfg.host, self.cfg.port)
        try:
            # Some RBN relays print a prompt; send the callsign unconditionally.
            writer.write((self.cfg.callsign + "\n").encode("ascii", "ignore"))
            await writer.drain()
            log.info("[RBN] connected to %s:%d", self.cfg.host, self.cfg.port)

            while True:
                raw = await reader.readline()
                if not raw:
                    break
                line = raw.decode("ascii", "ignore").strip()
                if not line or not line.upper().startswith("DX DE"):
                    continue
                spot = parse_cluster_line(line, source=Source.RBN, source_type=SourceType.SKIMMER)
                if spot is not None:
                    await self.emit(spot)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass