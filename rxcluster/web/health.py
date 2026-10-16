"""Minimal HTTP server exposing health and Prometheus-style metrics.

Implemented with :func:`asyncio.start_server` to avoid an HTTP framework
dependency. Only two endpoints are supported: ``GET /health`` and
``GET /metrics`` (the latter when enabled in the configuration).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable

from ..config import Config
from ..models import SpotStats

log = logging.getLogger(__name__)

CRLF = "\r\n"


class HealthServer:
    def __init__(
        self,
        cfg: Config,
        stats_provider: Callable[[], SpotStats],
        extras_provider: Callable[[], dict[str, int]] | None = None,
    ) -> None:
        self.cfg = cfg
        self.stats_provider = stats_provider
        self.extras_provider = extras_provider
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> None:
        hcfg = self.cfg.server.http
        if not hcfg.enabled:
            return
        self._server = await asyncio.start_server(self._handle, hcfg.host, hcfg.port)
        log.info("health server listening on %s:%d", hcfg.host, hcfg.port)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request_line = await reader.readline()
            path = "/"
            parts = request_line.decode("ascii", "ignore").split()
            if len(parts) >= 2:
                path = parts[1]
            # Drain headers.
            while True:
                header = await reader.readline()
                if header in (b"\r\n", b"\n", b""):
                    break
            body, content_type, status = self._respond(path)
            payload = body.encode("utf-8")
            headers = (
                f"HTTP/1.1 {status}{CRLF}"
                f"Content-Type: {content_type}{CRLF}"
                f"Content-Length: {len(payload)}{CRLF}"
                f"Connection: close{CRLF}{CRLF}"
            )
            writer.write(headers.encode("ascii") + payload)
            await writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    def _respond(self, path: str) -> tuple[str, str, str]:
        if path.startswith("/health"):
            stats = self.stats_provider()
            body = json.dumps({"status": "ok", "forwarded": stats.forwarded})
            return body, "application/json", "200 OK"
        if path.startswith("/metrics"):
            if not self.cfg.server.http.metrics_enabled:
                return "not found", "text/plain", "404 Not Found"
            return self._metrics(), "text/plain; version=0.0.4", "200 OK"
        return "not found", "text/plain", "404 Not Found"

    def _metrics(self) -> str:
        stats = self.stats_provider()
        lines = [
            "# HELP rxcluster_spots_total Spots received from all sources.",
            "# TYPE rxcluster_spots_total counter",
            f"rxcluster_spots_total {stats.received}",
            "# HELP rxcluster_spots_deduped_total Spots suppressed as duplicates.",
            "# TYPE rxcluster_spots_deduped_total counter",
            f"rxcluster_spots_deduped_total {stats.deduped}",
            "# HELP rxcluster_spots_rejected_total Spots rejected by validation.",
            "# TYPE rxcluster_spots_rejected_total counter",
            f"rxcluster_spots_rejected_total {stats.rejected}",
            "# HELP rxcluster_spots_forwarded_total Spots forwarded to at least one client.",
            "# TYPE rxcluster_spots_forwarded_total counter",
            f"rxcluster_spots_forwarded_total {stats.forwarded}",
        ]
        for source, count in stats.by_source.items():
            lines.append(f'rxcluster_spots_by_source_total{{source="{source}"}} {count}')
        if self.extras_provider is not None:
            for name, value in self.extras_provider().items():
                lines.append(f'rxcluster_{name} {value}')
        return "\n".join(lines) + "\n"