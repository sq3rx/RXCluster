"""Application entry point and async wiring."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import sys
from datetime import UTC, datetime

from .bus.pubsub import SpotBus
from .config import Config, load_config
from .datafiles import ensure_data_files
from .enrich.enricher import Enricher
from .models import Spot
from .parse.freq import BandPlan
from .pipeline import Pipeline
from .server.telnet import TelnetServer
from .sources.dxsummit import DxSummitConnector
from .sources.pskreporter import PskReporterConnector
from .sources.rbn import RbnConnector
from .sources.ve7cc import Ve7ccConnector
from .users.store import UserStore
from .validate.cty import CtyDatabase
from .validate.scp import ScpDatabase
from .validate.validator import Validator
from .web.health import HealthServer

log = logging.getLogger("rxcluster")


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def setup_logging(cfg: Config) -> None:
    level = getattr(logging, cfg.logging.level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    stream = logging.StreamHandler(sys.stdout)
    if cfg.logging.format == "json":
        stream.setFormatter(_JsonFormatter())
    else:
        stream.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root.addHandler(stream)

    if cfg.logging.file:
        file_handler = logging.FileHandler(cfg.logging.file, encoding="utf-8")
        file_handler.setFormatter(_JsonFormatter())
        root.addHandler(file_handler)


def _load_reference_data(cfg: Config) -> tuple[ScpDatabase, CtyDatabase]:
    scp = ScpDatabase()
    cty = CtyDatabase()
    try:
        if scp.load(cfg.data.scp_file):
            log.info("SCP loaded: %d callsigns", len(scp))
    except FileNotFoundError:
        log.warning("SCP file %s not found; SCP validation disabled", cfg.data.scp_file)
    try:
        if cty.load(cfg.data.cty_file):
            log.info("cty.dat loaded: %d prefixes", len(cty))
            if len(cty) < 1000:
                log.warning(
                    "cty.dat looks malformed (%d prefixes); geography filters "
                    "(DXCONT/DECONT, DXDXCC/DEDXCC) and CQ-zone/grid enrichment "
                    "will be wrong - re-download the file",
                    len(cty),
                )
    except FileNotFoundError:
        log.warning("cty file %s not found; geography enrichment disabled", cfg.data.cty_file)
    return scp, cty


async def _consume(queue: asyncio.Queue[Spot], pipeline: Pipeline) -> None:
    while True:
        spot = await queue.get()
        try:
            pipeline.process(spot)
        except Exception:  # pragma: no cover - defensive
            log.exception("error processing spot")


async def _solar_loop(enricher: Enricher, refresh_hours: float) -> None:
    while True:
        try:
            await enricher.refresh_solar()
            log.info("solar indices refreshed (ssn=%s)", getattr(enricher.voacap, "ssn", None))
        except Exception as exc:  # pragma: no cover
            log.warning("solar refresh failed: %s", exc)
        try:
            await enricher.precompute()
        except Exception as exc:  # pragma: no cover
            log.warning("VOACAP precompute failed: %s", exc)
        await asyncio.sleep(max(refresh_hours, 1.0) * 3600.0)


async def _data_loop(cfg: Config) -> None:
    while True:
        await asyncio.sleep(max(cfg.data.update_interval_hours, 1.0) * 3600.0)
        try:
            await ensure_data_files(cfg.data)
        except Exception as exc:  # pragma: no cover
            log.warning("data update failed: %s", exc)


async def run(cfg: Config) -> None:
    # Reference data (download if configured and missing).
    if cfg.data.auto_update:
        try:
            await ensure_data_files(cfg.data)
        except Exception as exc:  # pragma: no cover
            log.warning("initial data download failed: %s", exc)

    scp, cty = _load_reference_data(cfg)

    tags = cfg.pipeline.enrichment.tags
    if (tags.path or tags.confidence) and cfg.server.telnet.line_width != 76:
        log.warning(
            "N2WQ tags require a 76-character line; line_width=%d shifts the "
            "propagation/confidence columns and N1MM may not display them",
            cfg.server.telnet.line_width,
        )
    if tags.path and not cfg.station.operator_grid:
        log.warning(
            "propagation tags are enabled but station.operator_grid is unset; "
            "path glyphs will be blank (set a Maidenhead grid)"
        )

    band_plan = BandPlan(cfg.band_ranges, cfg.mode_subbands)
    validator = Validator(cfg.pipeline.validation, scp, cty)
    enricher = Enricher(cfg.pipeline.enrichment, cfg.station.operator_grid)
    bus = SpotBus()
    pipeline = Pipeline(
        cfg.pipeline,
        band_plan,
        validator,
        enricher,
        bus,
        line_width=cfg.server.telnet.line_width,
    )

    raw_queue: asyncio.Queue[Spot] = asyncio.Queue(maxsize=max(cfg.pipeline.raw_queue_size, 1))

    async def emit(spot: Spot) -> None:
        try:
            raw_queue.put_nowait(spot)
        except asyncio.QueueFull:
            try:
                raw_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                raw_queue.put_nowait(spot)
            except asyncio.QueueFull:
                pass

    connectors = []
    if cfg.sources.rbn.enabled:
        connectors.append(RbnConnector(cfg.sources.rbn, emit))
    if cfg.sources.dxsummit.enabled:
        connectors.append(DxSummitConnector(cfg.sources.dxsummit, emit))
    if cfg.sources.ve7cc.enabled:
        connectors.append(Ve7ccConnector(cfg.sources.ve7cc, emit))
    if cfg.sources.psk_reporter.enabled:
        connectors.append(PskReporterConnector(cfg.sources.psk_reporter, emit))

    telnet = TelnetServer(cfg, pipeline, bus, user_store=UserStore(cfg.users))
    health = HealthServer(
        cfg,
        stats_provider=lambda: pipeline.stats,
        extras_provider=lambda: {
            "clients": telnet.client_count,
            "subscribers": bus.subscriber_count,
            "queue_depth": raw_queue.qsize(),
        },
    )

    tasks = [asyncio.create_task(_consume(raw_queue, pipeline), name="consume")]
    for connector in connectors:
        tasks.append(asyncio.create_task(connector.run(), name=f"source:{connector.name}"))
    if enricher.voacap is not None:
        tasks.append(
            asyncio.create_task(
                _solar_loop(enricher, cfg.pipeline.enrichment.voacap.refresh_hours), name="solar"
            )
        )
    if cfg.data.auto_update:
        tasks.append(asyncio.create_task(_data_loop(cfg), name="datafiles"))

    await telnet.start()
    await health.start()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # Windows
            signal.signal(sig, lambda *_: stop.set())

    log.info(
        "RXCluster started (callsign=%s, grid=%s)",
        cfg.station.callsign,
        cfg.station.operator_grid,
    )
    try:
        await stop.wait()
    finally:
        log.info("shutting down")
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await telnet.stop()
        await health.stop()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rxcluster", description="DX Cluster aggregator/proxy")
    parser.add_argument(
        "--config", "-c", default="config/rxcluster.yaml", help="path to YAML config"
    )
    parser.add_argument("--version", action="store_true", help="print version and exit")
    args = parser.parse_args(argv)

    if args.version:
        from . import __version__

        print(__version__)
        return 0

    cfg = load_config(args.config)
    setup_logging(cfg)

    try:
        import uvloop  # type: ignore

        uvloop.install()
        log.debug("uvloop installed")
    except ImportError:
        pass

    try:
        asyncio.run(run(cfg))
    except KeyboardInterrupt:  # pragma: no cover
        pass
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())