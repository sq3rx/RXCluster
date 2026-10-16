"""PSKReporter MQTT connector.

PSKReporter (https://pskreporter.info) aggregates digimode reception reports
from thousands of automated receivers. Tom M0LTE redistributes the live feed
over MQTT at ``mqtt.pskreporter.info``, one JSON document per spot, on the
topic::

    pskr/filter/v2/{band}/{mode}/{tx}/{rx}/{tx_grid}/{rx_grid}/{tx_dxcc}/{rx_dxcc}

The feed is push-based, so the connector subscribes and forwards every payload
it receives. The global feed is very high volume; narrow ``topic`` (e.g.
``pskr/filter/v2/20m/FT8/#``) to restrict what the broker delivers.
"""

from __future__ import annotations

import logging
import os
import time

import aiomqtt
import orjson

from ..config import PskReporterConfig
from ..models import Mode, Source, SourceType, Spot
from .base import SourceConnector

log = logging.getLogger(__name__)

# ADIF mode/submode -> normalized Mode. Anything else becomes Mode.UNKNOWN.
_MODE_MAP: dict[str, Mode] = {
    "CW": Mode.CW,
    "RTTY": Mode.RTTY,
    "SSB": Mode.SSB,
    "USB": Mode.SSB,
    "LSB": Mode.SSB,
    "FT8": Mode.FT8,
    "FT4": Mode.FT4,
    "PSK": Mode.PSK,
    "PSK31": Mode.PSK,
    "PSK63": Mode.PSK,
    "PSK125": Mode.PSK,
    "BPSK": Mode.PSK,
}


def adif_mode(value: object) -> Mode:
    """Map a PSKReporter ADIF mode string to the normalized :class:`Mode`."""
    if not isinstance(value, str):
        return Mode.UNKNOWN
    return _MODE_MAP.get(value.strip().upper(), Mode.UNKNOWN)


class PskReporterConnector(SourceConnector):
    name = "PSKREPORTER"

    def __init__(self, cfg: PskReporterConfig, emit) -> None:
        super().__init__(emit, cfg.reconnect_delay, cfg.max_reconnect_delay)
        self.cfg = cfg

    async def _stream_once(self) -> None:
        identifier = self.cfg.client_id or f"rxcluster-{os.getpid()}"
        tls_params = aiomqtt.TLSParameters() if self.cfg.tls else None
        async with aiomqtt.Client(
            hostname=self.cfg.host,
            port=self.cfg.port,
            identifier=identifier,
            keepalive=self.cfg.keepalive,
            tls_params=tls_params,
        ) as client:
            await client.subscribe(self.cfg.topic, qos=0)
            log.info(
                "[PSKREPORTER] connected to %s:%d topic=%s",
                self.cfg.host,
                self.cfg.port,
                self.cfg.topic,
            )
            async for message in client.messages:
                payload = message.payload
                if not isinstance(payload, (bytes, bytearray)):
                    continue
                spot = self._to_spot(bytes(payload))
                if spot is not None:
                    await self.emit(spot)

    @staticmethod
    def _to_spot(payload: bytes) -> Spot | None:
        """Normalize one PSKReporter MQTT payload into a :class:`Spot`.

        The sender of a reception report is the station being heard (the DX),
        and the receiver is the spotting station.
        """
        try:
            record = orjson.loads(payload)
        except orjson.JSONDecodeError:
            return None
        if not isinstance(record, dict):
            return None

        dx_call = str(record.get("sc") or "").strip().upper()
        if not dx_call:
            return None

        try:
            freq_hz = float(record.get("f") or 0.0)
        except (TypeError, ValueError):
            return None
        if freq_hz <= 0:
            return None

        spotter = str(record.get("rc") or "").strip().upper() or "PSKREPORTER"

        try:
            timestamp = float(record.get("t") or 0.0)
        except (TypeError, ValueError):
            timestamp = 0.0
        if timestamp <= 0:
            timestamp = time.time()

        snr: int | None = None
        raw_snr = record.get("rp")
        if isinstance(raw_snr, (int, float)):
            snr = int(raw_snr)

        return Spot(
            source=Source.PSKREPORTER,
            source_type=SourceType.SKIMMER,
            spotter=spotter,
            dx_call=dx_call,
            freq_khz=freq_hz / 1000.0,
            timestamp=timestamp,
            mode=adif_mode(record.get("md")),
            snr=snr,
            dx_grid=str(record.get("sl") or "").strip().upper(),
            spotter_grid=str(record.get("rl") or "").strip().upper(),
        )