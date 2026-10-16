"""Propagation prediction engine.

RXCluster uses VOACAP to estimate the chance of a QSO between the operator's
QTH and a spotted station.

Two engines are supported:

* **voacapl** - the real VOACAP engine (compiled into the container image).
  Reliability is precomputed in the background into a coverage matrix keyed by
  ``(target_grid_cell, band, hour)``, so per-spot lookups are O(1). The matrix
  is refreshed whenever the solar indices or month change.
* **empirical fallback** - a dependency-free heuristic based on great-circle
  distance, solar zenith angle at the mid-path and the smoothed sunspot number.
  Used when ``voacapl`` is unavailable or a cell has not been computed yet.

The empirical model also serves as the immediate answer before the first
(precompute) VOACAP run completes, so the spot stream is never blocked.
"""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import UTC, datetime

from ...config import VoacapConfig
from ...grid import distance_km, grid_to_latlon
from ...models import PathClass
from .solar import SolarProvider
from .voacapl import (
    BAND_FREQ_INDEX,
    FREQS_MHZ,
    VoacaplRunner,
    build_deck,
    nearest_rel,
    parse_rel,
    rel_to_path,
)

log = logging.getLogger(__name__)


def _solar_zenith(lat: float, lon: float, dt: datetime) -> float:
    """Approximate solar zenith angle in degrees."""
    day_of_year = dt.timetuple().tm_yday
    hour = dt.hour + dt.minute / 60.0
    decl = 23.44 * math.radians(math.sin(math.radians(360 / 365 * (day_of_year - 81))))
    solar_time = hour + lon / 15.0
    hour_angle = math.radians((solar_time - 12.0) * 15.0)
    lat_rad = math.radians(lat)
    cos_zenith = math.sin(lat_rad) * math.sin(decl) + math.cos(lat_rad) * math.cos(decl) * math.cos(
        hour_angle
    )
    cos_zenith = max(-1.0, min(1.0, cos_zenith))
    return math.degrees(math.acos(cos_zenith))


class VoacapEngine:
    def __init__(self, cfg: VoacapConfig, operator_grid: str) -> None:
        self.cfg = cfg
        self.operator_grid = operator_grid or ""
        self.operator_pos = grid_to_latlon(self.operator_grid) if self.operator_grid else None
        self.solar = SolarProvider(cfg.solar_source, cfg.ssn_default)
        self.runner = VoacaplRunner(cfg.engine_path, cfg.itshfbc_dir)
        self._cache: dict[tuple[str, str, int, int], PathClass] = {}
        self._matrix: dict[tuple[str, str, int], PathClass] = {}
        self._precompute_lock = asyncio.Lock()
        self._cell_degrees = max(1, cfg.target_grid_degrees)

        if self.runner.available:
            log.info(
                "voacapl engine ready (engine=%s, itshfbc=%s)",
                self.runner.engine,
                self.runner.itshfbc,
            )
        else:
            log.info("voacapl not available; using empirical propagation fallback")

    @property
    def ssn(self) -> int:
        return self.solar.ssn

    @property
    def matrix_size(self) -> int:
        return len(self._matrix)

    async def refresh_solar(self) -> int:
        ssn = await self.solar.refresh()
        self._cache.clear()
        self._matrix.clear()
        return ssn

    # -- cell helpers ------------------------------------------------------
    def _cell_key(self, lat: float, lon: float) -> str:
        step = self._cell_degrees
        clat = int(round(lat / step)) * step
        clon = int(round(lon / step)) * step
        return f"{clat}:{clon}"

    def _all_cells(self) -> list[tuple[float, float]]:
        step = self._cell_degrees
        cells: list[tuple[float, float]] = []
        lat = -90
        while lat <= 90:
            lon = -180
            while lon <= 180:
                cells.append((float(lat), float(lon)))
                lon += step
            lat += step
        return cells

    # -- prediction --------------------------------------------------------
    def predict(
        self,
        target_grid: str,
        band: str,
        freq_khz: float,
        mode: str,
        when: datetime | None = None,
    ) -> PathClass:
        if not self.cfg.enabled or self.operator_pos is None or not target_grid:
            return PathClass.INSUFFICIENT
        when = when or datetime.now(UTC)
        target = grid_to_latlon(target_grid)
        if target is None:
            return PathClass.INSUFFICIENT

        # Preferred path: precomputed VOACAP matrix.
        if band in BAND_FREQ_INDEX:
            cell = self._cell_key(target[0], target[1])
            cached = self._matrix.get((cell, band, when.hour))
            if cached is not None:
                return cached

        # Fallback: memoized empirical model.
        key = (target_grid.upper()[:4], band, when.hour, self.ssn)
        cached_emp = self._cache.get(key)
        if cached_emp is not None:
            return cached_emp
        result = self._empirical(target_grid, freq_khz, when)
        self._cache[key] = result
        if len(self._cache) > 200000:
            self._cache.clear()
            self._cache[key] = result
        return result

    # -- precompute --------------------------------------------------------
    async def precompute(self) -> int:
        """(Re)build the VOACAP coverage matrix. Returns the number of cells."""
        if not self.runner.available or self.operator_pos is None or not self.cfg.enabled:
            return 0
        if not self.cfg.precompute:
            return 0
        async with self._precompute_lock:
            now = datetime.now(UTC)
            op_lat, op_lon = self.operator_pos
            ssn = self.ssn
            matrix: dict[tuple[str, str, int], PathClass] = {}
            cells = self._all_cells()
            log.info("precomputing VOACAP matrix for %d grid cells", len(cells))
            for rx_lat, rx_lon in cells:
                deck = build_deck(
                    op_lat, op_lon, rx_lat, rx_lon, now.year, now.month, ssn, FREQS_MHZ
                )
                tag = f"{int(rx_lat)}_{int(rx_lon)}"
                text = await asyncio.to_thread(self.runner.run, deck, tag)
                if text is None:
                    continue
                parsed = parse_rel(text)
                cell = self._cell_key(rx_lat, rx_lon)
                for band, index in BAND_FREQ_INDEX.items():
                    target_mhz = FREQS_MHZ[index]
                    for hour in range(1, 25):
                        rows = parsed.get(hour)
                        if not rows:
                            continue
                        matrix[(cell, band, hour)] = rel_to_path(nearest_rel(rows, target_mhz))
                # Yield to the event loop between cells.
                await asyncio.sleep(0)
            self._matrix = matrix
            log.info("VOACAP matrix ready: %d entries", len(matrix))
            return len(cells)

    # -- empirical fallback ------------------------------------------------
    def _empirical(self, target_grid: str, freq_khz: float, when: datetime) -> PathClass:
        target = grid_to_latlon(target_grid)
        if target is None or self.operator_pos is None:
            return PathClass.INSUFFICIENT
        op_lat, op_lon = self.operator_pos
        t_lat, t_lon = target
        dist = distance_km(op_lat, op_lon, t_lat, t_lon)
        mid_lat = (op_lat + t_lat) / 2.0
        mid_lon = (op_lon + t_lon) / 2.0

        zenith = _solar_zenith(mid_lat, mid_lon, when)
        day_factor = max(0.12, math.cos(math.radians(zenith)))

        freq_mhz = freq_khz / 1000.0
        muf = (6.0 + 0.16 * self.ssn) * day_factor
        if dist > 8000:
            muf *= 0.85
        elif dist > 4000:
            muf *= 0.95
        luf = 1.5 + 2.0 * (1.0 - day_factor)

        if dist < 600 and freq_mhz < 8.0:
            return PathClass.HIGH if day_factor > 0.3 else PathClass.MEDIUM

        if freq_mhz > muf * 1.15:
            return PathClass.CLOSED
        if freq_mhz > muf:
            return PathClass.UNLIKELY
        if freq_mhz < luf:
            return PathClass.LOW if dist < 3000 else PathClass.UNLIKELY

        upper_margin = (muf - freq_mhz) / max(muf, 1e-6)
        lower_margin = (freq_mhz - luf) / max(luf, 1e-6)
        margin = min(upper_margin / 0.35, lower_margin / 0.5 if luf > 0 else 1.0)
        if margin >= 0.6:
            return PathClass.HIGH
        if margin >= 0.3:
            return PathClass.MEDIUM
        return PathClass.LOW