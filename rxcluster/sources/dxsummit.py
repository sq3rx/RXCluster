"""DX Summit connector (HTTP JSON API).

DX Summit has no streaming telnet feed for spot consumption; instead it offers
a JSON API. The connector polls it at a configurable interval and de-duplicates
records it has already seen by their API id.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime

import httpx

from ..config import DxSummitConfig
from ..grid import latlon_to_grid
from ..models import Mode, Source, SourceType, Spot
from ..parse.cluster_line import is_beacon, parse_comment
from .base import SourceConnector

log = logging.getLogger(__name__)


def _parse_timestamp(value) -> float:
    if isinstance(value, (int, float)):
        # Heuristic: milliseconds vs seconds.
        return float(value) / 1000.0 if value > 1e11 else float(value)
    if isinstance(value, str):
        text = value.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text).replace(tzinfo=UTC).timestamp()
        except ValueError:
            pass
    return time.time()


def _grid_from(record: dict, lat_key: str, lon_key: str) -> str:
    """Derive a 4-character Maidenhead locator from DX Summit coordinates.

    DX Summit reports longitudes with **west as positive**, the opposite of the
    standard east-positive convention, so the sign is flipped before encoding.
    """
    lat = record.get(lat_key)
    lon = record.get(lon_key)
    if lat is None or lon is None:
        return ""
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        return ""
    if not -90.0 <= lat_f <= 90.0 or not -180.0 <= lon_f <= 180.0:
        return ""
    return latlon_to_grid(lat_f, -lon_f, precision=4)


class DxSummitConnector(SourceConnector):
    name = "DXSUMMIT"

    def __init__(self, cfg: DxSummitConfig, emit) -> None:
        super().__init__(emit)
        self.cfg = cfg
        self._seen_ids: set[str] = set()

    async def _stream_once(self) -> None:
        async with httpx.AsyncClient() as client:
            while True:
                try:
                    await self._poll(client)
                except Exception as exc:  # network / parse error
                    log.warning("[DXSUMMIT] poll failed: %s", exc)
                await asyncio.sleep(self.cfg.poll_interval)

    async def _poll(self, client: httpx.AsyncClient) -> None:
        params = {"limit": str(self.cfg.limit)}
        resp = await client.get(self.cfg.api_url, params=params, timeout=self.cfg.timeout)
        resp.raise_for_status()
        payload = resp.json()
        records = payload if isinstance(payload, list) else payload.get("spots", [])
        for record in records:
            if not isinstance(record, dict):
                continue
            spot = self._to_spot(record)
            if spot is not None:
                await self.emit(spot)

    def _to_spot(self, record: dict) -> Spot | None:
        rec_id = str(record.get("id", ""))
        if rec_id:
            if rec_id in self._seen_ids:
                return None
            self._seen_ids.add(rec_id)
            if len(self._seen_ids) > 20000:
                self._seen_ids.clear()

        dx_call = (
            record.get("dx_call") or record.get("callsign") or record.get("dx") or ""
        ).strip().upper()
        spotter = (
            record.get("de_call") or record.get("spotter") or record.get("de") or "DXSUMMIT"
        ).strip().upper()
        if not dx_call:
            return None

        try:
            freq = float(record.get("frequency") or record.get("freq") or 0.0)
        except (TypeError, ValueError):
            return None
        if freq <= 0:
            return None
        if freq < 1000:  # API returned MHz
            freq *= 1000.0

        raw_comment = (record.get("comment") or record.get("info") or "").strip()
        api_mode = record.get("mode")
        if isinstance(api_mode, str) and api_mode.strip():
            # Prepend the explicit API mode so parse_comment can capture it.
            raw_comment = f"{api_mode.strip()} {raw_comment}".strip()

        mode, snr, wpm, comment = parse_comment(raw_comment)

        return Spot(
            source=Source.DXSUMMIT,
            source_type=SourceType.HUMAN,
            spotter=spotter,
            dx_call=dx_call,
            freq_khz=freq,
            timestamp=_parse_timestamp(record.get("time") or record.get("timestamp")),
            comment=comment,
            mode=mode or Mode.UNKNOWN,
            snr=snr,
            speed_wpm=wpm,
            dx_grid=_grid_from(record, "dx_latitude", "dx_longitude"),
            spotter_grid=_grid_from(record, "de_latitude", "de_longitude"),
            is_beacon=is_beacon(comment, dx_call),
        )