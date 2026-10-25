import asyncio

import pytest

from rxcluster.bus.pubsub import SpotBus
from rxcluster.config import Config, UserStoreConfig
from rxcluster.enrich.enricher import Enricher
from rxcluster.models import Mode, Source, SourceType, Spot
from rxcluster.parse.freq import BandPlan
from rxcluster.pipeline import Pipeline
from rxcluster.server.telnet import TelnetServer
from rxcluster.users.store import UserStore
from rxcluster.validate.cty import CtyDatabase
from rxcluster.validate.scp import ScpDatabase
from rxcluster.validate.validator import Validator


def build_app(user_store: UserStore | None = None) -> tuple[Config, Pipeline, TelnetServer]:
    cfg = Config()
    cfg.server.telnet.host = "127.0.0.1"
    cfg.server.telnet.port = 0
    cfg.pipeline.enrichment.voacap.enabled = False

    band_plan = BandPlan(cfg.band_ranges, cfg.mode_subbands)
    validator = Validator(cfg.pipeline.validation, ScpDatabase(), CtyDatabase())
    enricher = Enricher(cfg.pipeline.enrichment, cfg.station.operator_grid)
    bus = SpotBus()
    pipeline = Pipeline(cfg.pipeline, band_plan, validator, enricher, bus)
    server = TelnetServer(cfg, pipeline, bus, user_store=user_store)
    return cfg, pipeline, server


def _spot(dx_call: str, freq_khz: float, mode: Mode) -> Spot:
    return Spot(
        source=Source.RBN,
        source_type=SourceType.SKIMMER,
        spotter="W3LPL",
        dx_call=dx_call,
        freq_khz=freq_khz,
        timestamp=0.0,
        mode=mode,
    )


def test_recent_search_prefix_band_mode_and_predicate():
    _cfg, pipeline, _server = build_app()
    pipeline.process(_spot("K1ABC", 7005.0, Mode.CW))
    pipeline.process(_spot("DL1ABC", 14025.0, Mode.CW))
    pipeline.process(_spot("W1XYZ", 14074.0, Mode.FT8))

    assert len(pipeline.recent_search(count=10)) == 3
    assert len(pipeline.recent_search(count=2)) == 2

    dl = pipeline.recent_search(dx_call="DL", band="20m", mode="CW")
    assert len(dl) == 1 and "DL1ABC" in dl[0]

    assert len(pipeline.recent_search(dx_call="DL1")) == 1
    assert len(pipeline.recent_search(dx_call="*ABC")) == 2
    assert pipeline.recent_search(dx_call="N0CALL") == []

    only_40 = pipeline.recent_search(predicate=lambda s: s.band == "40m")
    assert len(only_40) == 1 and "K1ABC" in only_40[0]


@pytest.mark.asyncio
async def test_telnet_sh_dx_filtered_per_user():
    _cfg, pipeline, server = build_app()
    await server.start()
    port = server._server.sockets[0].getsockname()[1]

    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        await asyncio.wait_for(reader.readline(), 2)
        writer.write(b"N0CALL\n")
        await writer.drain()
        await asyncio.wait_for(reader.readline(), 2)

        pipeline.process(_spot("K1ABC", 7005.0, Mode.CW))  # 40m
        pipeline.process(_spot("DL1ABC", 14025.0, Mode.CW))  # 20m
        await asyncio.sleep(0.2)

        writer.write(b"REJECT BAND 40m\n")
        await writer.drain()
        await _read_until(reader, b"REJECT BAND")

        writer.write(b"SH/DX\n")
        await writer.drain()
        reply = await _read_until(reader, b"DL1ABC")
        assert b"DL1ABC" in reply
        assert b"K1ABC" not in reply

        writer.write(b"SH/DX K1ABC\n")
        await writer.drain()
        empty = await _read_until(reader, b"No spots available.")
        assert b"No spots available." in empty
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        await server.stop()


@pytest.mark.asyncio
async def test_telnet_streams_spot():
    _cfg, pipeline, server = build_app()
    await server.start()
    assert server._server is not None
    port = server._server.sockets[0].getsockname()[1]

    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        banner = await asyncio.wait_for(reader.readline(), 2)
        assert b"RXCluster" in banner

        writer.write(b"N0CALL\n")
        await writer.drain()
        connected = await asyncio.wait_for(reader.readline(), 2)
        assert b"Connected" in connected

        spot = Spot(
            source=Source.RBN,
            source_type=SourceType.SKIMMER,
            spotter="W3LPL",
            dx_call="K1ABC",
            freq_khz=7005.0,
            timestamp=0.0,
            mode=Mode.CW,
        )
        pipeline.process(spot)
        line = await asyncio.wait_for(reader.readline(), 2)
        assert b"DX de W3LPL-#:" in line
        assert b"K1ABC" in line
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        await server.stop()


@pytest.mark.asyncio
async def test_telnet_command_filter():
    _cfg, pipeline, server = build_app()
    await server.start()
    port = server._server.sockets[0].getsockname()[1]

    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        await asyncio.wait_for(reader.readline(), 2)
        writer.write(b"N0CALL\n")
        await writer.drain()
        await asyncio.wait_for(reader.readline(), 2)

        writer.write(b"REJECT BAND 40m\n")
        await writer.drain()
        response = await asyncio.wait_for(reader.readline(), 2)
        assert b"REJECT BAND" in response
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        await server.stop()


async def _read_until(reader, needle: bytes, timeout: float = 3.0) -> bytes:
    collected = b""
    while needle not in collected:
        line = await asyncio.wait_for(reader.readline(), timeout)
        if not line:
            break
        collected += line
    return collected


@pytest.mark.asyncio
async def test_telnet_show_filter_and_post():
    _cfg, pipeline, server = build_app()
    await server.start()
    port = server._server.sockets[0].getsockname()[1]

    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        await asyncio.wait_for(reader.readline(), 2)
        writer.write(b"N0CALL\n")
        await writer.drain()
        await asyncio.wait_for(reader.readline(), 2)

        writer.write(b"SHOW FILTER FULL\n")
        await writer.drain()
        shown = await _read_until(reader, b"SWITCHES")
        assert b"BAND" in shown
        assert b"SWITCHES" in shown

        writer.write(b"DX 14025.0 K1ABC CQ test\n")
        await writer.drain()
        posted = await _read_until(reader, b"Spot accepted.")
        assert b"Spot accepted." in posted
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        await server.stop()


@pytest.mark.asyncio
async def test_telnet_persists_settings_per_callsign(tmp_path):
    store = UserStore(UserStoreConfig(directory=str(tmp_path)))
    _cfg, _pipeline, server = build_app(user_store=store)
    await server.start()
    port = server._server.sockets[0].getsockname()[1]

    async def login(writer):
        await asyncio.wait_for(reader.readline(), 2)
        writer.write(b"SQ9ABC\n")
        await writer.drain()
        await asyncio.wait_for(reader.readline(), 2)

    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        await login(writer)
        writer.write(b"REJECT BAND 40m\n")
        await writer.drain()
        await asyncio.wait_for(reader.readline(), 2)
        writer.write(b"SET GRID JO90AA\n")
        await writer.drain()
        await asyncio.wait_for(reader.readline(), 2)
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass

    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        await login(writer)
        writer.write(b"SHOW FILTER\n")
        await writer.drain()
        shown = await _read_until(reader, b"block 40m")
        assert b"block 40m" in shown
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        await server.stop()
