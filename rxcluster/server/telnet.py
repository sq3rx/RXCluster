"""Asyncio telnet server speaking the DX cluster protocol to N1MM Logger+.

Design notes
------------
* Every client is decoupled from the pipeline by its own :class:`Subscriber`
  queue; the writer task can block on a slow TCP peer without stalling ingest.
* ``TCP_NODELAY`` is enabled to minimize latency.
* On connect the server prompts for a callsign, then streams spots. A subset of
  the N2WQ/CC/DX Spider command dialect is supported.
"""

from __future__ import annotations

import asyncio
import logging
import socket
import time

from ..bus.pubsub import SpotBus, Subscriber
from ..config import Config, UserStoreConfig
from ..filters.compiled import compile_filter
from ..filters.model import FilterState, default_state_from_config
from ..filters.nearby import NearbyFilter, NearbySpec
from ..pipeline import Pipeline
from ..users.store import UserStore
from .commands import ClientSession, execute_command

log = logging.getLogger(__name__)

CRLF = "\r\n"


class TelnetServer:
    def __init__(
        self,
        cfg: Config,
        pipeline: Pipeline,
        bus: SpotBus,
        user_store: UserStore | None = None,
    ) -> None:
        self.cfg = cfg
        self.pipeline = pipeline
        self.bus = bus
        # When not injected, persistence is disabled so tests and embedders do
        # not touch the filesystem unexpectedly.
        self.user_store = user_store or UserStore(UserStoreConfig(enabled=False))
        self._server: asyncio.AbstractServer | None = None
        self._clients: set[ClientSession] = set()

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def start(self) -> None:
        tcfg = self.cfg.server.telnet
        self._server = await asyncio.start_server(self._handle_client, tcfg.host, tcfg.port)
        addrs = ", ".join(str(sock.getsockname()) for sock in (self._server.sockets or []))
        log.info("telnet server listening on %s", addrs)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        tcfg = self.cfg.server.telnet
        peer = writer.get_extra_info("peername")
        if self.client_count >= tcfg.max_clients:
            writer.write(f"*** {tcfg.banner}: too many clients{CRLF}".encode())
            await writer.drain()
            writer.close()
            return

        try:
            sock = writer.get_extra_info("socket")
            if sock is not None:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass

        writer.write((f"*** {tcfg.banner}{CRLF}").encode())
        writer.write(b"login: ")
        await writer.drain()

        login_raw = await reader.readline()
        callsign = login_raw.decode("ascii", "ignore").strip().upper() or "N0CALL"

        state = default_state_from_config(self.cfg.defaults)
        grid = self.cfg.station.operator_grid
        noise = self.cfg.station.noise_class
        dedupe = "SLOW"
        nearby = NearbySpec.from_config(self.cfg.pipeline.nearby)
        record = self.user_store.load(callsign)
        if record:
            stored_filter = record.get("filter")
            if isinstance(stored_filter, dict):
                state = FilterState.from_dict(stored_filter)
                # Migrate the pre-0.3.0 NEARBY flag that lived in the filter.
                if stored_filter.get("nearby") is True:
                    nearby.enabled = True
            grid = str(record.get("grid", grid))
            noise = str(record.get("noise", noise))
            dedupe = str(record.get("dedupe", dedupe))
            stored_nearby = record.get("nearby")
            if isinstance(stored_nearby, dict):
                if "enabled" in stored_nearby:
                    nearby.enabled = bool(stored_nearby["enabled"])
                if "radius_km" in stored_nearby:
                    try:
                        nearby.radius_km = float(stored_nearby["radius_km"])
                    except (TypeError, ValueError):
                        pass

        cty = self.pipeline.validator.cty
        compiled = compile_filter(state, callsign, cty)
        nearby_filter = NearbyFilter(
            grid, nearby, operator_call=callsign, bypass_own=state.switches.get("self", False)
        )
        dedup_cfg = self.cfg.pipeline.dedup
        subscriber = Subscriber(
            callsign,
            compiled,
            tcfg.client_queue_size,
            dedup_window_seconds=dedup_cfg.window_for(dedupe),
            freq_tolerance_khz=dedup_cfg.freq_tolerance_khz,
            nearby=nearby_filter,
        )
        self.bus.subscribe(subscriber)

        session = ClientSession(
            callsign=callsign,
            state=state,
            compiled=compiled,
            subscriber=subscriber,
            grid=grid,
            noise=noise,
            dedupe_policy=dedupe,
            cty=cty,
            nearby=nearby,
        )
        session.persist = lambda: self._persist(session)
        self._clients.add(session)
        log.info("client %s connected from %s", callsign, peer)

        writer.write(
            (
                f"*** Connected as {callsign}. "
                f"Type HELP for commands, BYE to disconnect.{CRLF}"
            ).encode()
        )
        await writer.drain()

        pump = asyncio.create_task(self._pump(subscriber, writer, session))
        try:
            await self._read_loop(reader, writer, session)
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            pump.cancel()
            self.bus.unsubscribe(subscriber)
            self._clients.discard(session)
            try:
                writer.write(f"*** 73 de RXCluster{CRLF}".encode())
                await writer.drain()
            except Exception:
                pass
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            log.info("client %s disconnected", callsign)

    def _persist(self, session: ClientSession) -> None:
        record = UserStore.build_record(
            session.callsign,
            session.state.to_dict(),
            grid=session.grid,
            noise=session.noise,
            dedupe=session.dedupe_policy,
            nearby={"enabled": session.nearby.enabled, "radius_km": session.nearby.radius_km},
        )
        self.user_store.save(session.callsign, record)

    async def _read_loop(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, session: ClientSession
    ) -> None:
        while True:
            raw = await reader.readline()
            if not raw:
                break
            line = raw.decode("ascii", "ignore").rstrip("\r\n")
            if not line.strip():
                # Keep-alive: N1MM sends a bare space periodically.
                continue
            result = execute_command(line, session, self.cfg, self.pipeline)
            for response in result.responses:
                writer.write((response + CRLF).encode("ascii", "ignore"))
            await writer.drain()
            if result.pause_seconds > 0:
                session.paused_until = max(
                    session.paused_until, time.monotonic() + result.pause_seconds
                )
            if result.disconnect:
                break

    async def _pump(
        self, subscriber: Subscriber, writer: asyncio.StreamWriter, session: ClientSession
    ) -> None:
        try:
            while True:
                line = await subscriber.get()
                if session.paused_until > time.monotonic():
                    session.suppressed += 1
                    continue
                writer.write((line + CRLF).encode("ascii", "ignore"))
                await writer.drain()
        except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError):
            return