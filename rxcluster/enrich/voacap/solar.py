"""Solar (SSN) index provider.

Fetches the smoothed sunspot number (SSN) from the NOAA SWPC JSON feed and
falls back to the configured default when the network is unavailable.
"""

from __future__ import annotations

import logging

import httpx

log = logging.getLogger(__name__)


class SolarProvider:
    def __init__(self, source_url: str, default_ssn: int = 100) -> None:
        self.source_url = source_url
        self.default_ssn = default_ssn
        self.ssn = default_ssn

    async def refresh(self, client: httpx.AsyncClient | None = None) -> int:
        """Fetch the latest SSN. Returns the value used."""
        try:
            if client is not None:
                resp = await client.get(self.source_url, timeout=15.0)
            else:
                async with httpx.AsyncClient() as local:
                    resp = await local.get(self.source_url, timeout=15.0)
            resp.raise_for_status()
            data = resp.json()
            ssn = self._extract_ssn(data)
            if ssn is not None:
                self.ssn = max(0, min(300, int(round(ssn))))
        except Exception as exc:  # network / parse errors are non-fatal
            log.warning("could not refresh solar indices: %s", exc)
        return self.ssn

    @staticmethod
    def _extract_ssn(data) -> float | None:
        if isinstance(data, list) and data:
            for entry in reversed(data):
                if isinstance(entry, dict) and "ssn" in entry:
                    try:
                        return float(entry["ssn"])
                    except (TypeError, ValueError):
                        continue
        if isinstance(data, dict) and "ssn" in data:
            try:
                return float(data["ssn"])
            except (TypeError, ValueError):
                return None
        return None