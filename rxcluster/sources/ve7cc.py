"""VE7CC (CC Cluster) telnet connector.

Used as the human-reported source: after login the connector requests a
human-only feed by disabling skimmer spots, so it complements the RBN feed
instead of duplicating it.
"""

from __future__ import annotations

import asyncio
import logging

from ..config import Ve7ccConfig
from ..models import Source, SourceType
from ..parse.cluster_line import parse_bulletin, parse_cluster_line
from .base import SourceConnector

log = logging.getLogger(__name__)


class Ve7ccConnector(SourceConnector):
    name = "VE7CC"

    def __init__(self, cfg: Ve7ccConfig, emit) -> None:
        super().__init__(emit, cfg.reconnect_delay, cfg.max_reconnect_delay)
        self.cfg = cfg

    async def _stream_once(self) -> None:
        reader, writer = await asyncio.open_connection(self.cfg.host, self.cfg.port)
        try:
            login = self.cfg.callsign
            if self.cfg.password:
                login = f"{login} {self.cfg.password}"
            writer.write((login + "\n").encode("ascii", "ignore"))
            await writer.drain()

            # Give the node a moment to process login, then apply preferences.
            await asyncio.sleep(0.5)
            cmd = "set/skimmer off\n" if self.cfg.human_only else "set/dx\n"
            writer.write(cmd.encode("ascii", "ignore"))
            await writer.drain()
            log.info(
                "[VE7CC] connected to %s:%d (human_only=%s)",
                self.cfg.host,
                self.cfg.port,
                self.cfg.human_only,
            )

            while True:
                raw = await reader.readline()
                if not raw:
                    break
                line = raw.decode("ascii", "ignore").strip()
                if line.upper().startswith("DX DE"):
                    spot = parse_cluster_line(
                        line, source=Source.VE7CC, source_type=SourceType.HUMAN
                    )
                    if spot is not None:
                        await self.emit(spot)
                    continue
                bulletin = parse_bulletin(line, source=Source.VE7CC)
                if bulletin is not None:
                    await self.emit(bulletin)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass