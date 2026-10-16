"""The processing pipeline.

Ties together normalization (band/mode), dedup, validation, enrichment and
fan-out. One instance is owned by the application and consumed by a single
asyncio task, so all stages can be non-thread-safe.
"""

from __future__ import annotations

import re
import time
from collections import deque
from datetime import UTC, datetime

from .bus.pubsub import SpotBus
from .config import PipelineConfig
from .dedup.window import DedupWindow
from .enrich.enricher import Enricher
from .enrich.voacap.voacapl import BAND_FREQ_INDEX, FREQS_MHZ
from .models import PATH_SYMBOL, PathClass, Source, SourceType, Spot, SpotKind, SpotStats
from .parse.freq import BandPlan
from .validate.validator import Validator

_GRID_RE = re.compile(r"^[A-Z]{2}[0-9]{2}[A-Z]{0,2}$")


class Pipeline:
    def __init__(
        self,
        cfg: PipelineConfig,
        band_plan: BandPlan,
        validator: Validator,
        enricher: Enricher,
        bus: SpotBus,
        line_width: int = 76,
        history_size: int = 200,
    ) -> None:
        self.cfg = cfg
        self.band_plan = band_plan
        self.validator = validator
        self.enricher = enricher
        self.bus = bus
        self.line_width = line_width
        self.stats = SpotStats()
        self.dedup = DedupWindow(cfg.dedup.window_seconds, cfg.dedup.freq_tolerance_khz)
        self._history: deque[tuple[Spot, str]] = deque(maxlen=history_size)

    def process(self, spot: Spot) -> bool:
        """Run one spot through the pipeline. Returns whether it was forwarded."""
        self.stats.received += 1
        self.stats.bump_source(spot.source)

        # Bulletins (WWV/WCY/ANNOUNCE) bypass normalization/validation.
        if spot.kind is not SpotKind.SPOT:
            line = self.enricher.render(spot, self.line_width)
            self._history.append((spot, line))
            delivered = self.bus.publish(spot, line)
            if delivered:
                self.stats.forwarded += 1
                return True
            return False

        # Normalize band and mode.
        spot.band = self.band_plan.band_for_freq(spot.freq_khz)
        spot.mode = self.band_plan.infer_mode(spot.freq_khz, spot.band, spot.mode)

        if self.dedup.is_duplicate(spot):
            self.stats.deduped += 1
            return False

        if not self.validator.process(spot):
            self.stats.rejected += 1
            return False

        self.enricher.process(spot)
        line = self.enricher.render(spot, self.line_width)
        self._history.append((spot, line))
        delivered = self.bus.publish(spot, line)
        if delivered:
            self.stats.forwarded += 1
            return True
        return False

    def post_manual(self, spotter: str, request) -> str:
        """Accept a manually posted spot (``DX`` command) and run it through."""
        spot = Spot(
            source=Source.MANUAL,
            source_type=SourceType.HUMAN,
            spotter=(spotter or "N0CALL").upper(),
            dx_call=request.dx_call,
            freq_khz=request.freq_khz,
            timestamp=time.time(),
            comment=request.comment,
        )
        return "Spot accepted." if self.process(spot) else "Spot rejected."

    def recent(self, count: int) -> list[str]:
        """Return up to ``count`` most recent rendered lines (oldest first)."""
        items = list(self._history)[-count:]
        return [line for _, line in items]

    def recent_for(self, dx_call: str, count: int) -> list[str]:
        call = dx_call.upper()
        matches = [line for spot, line in self._history if spot.dx_call.upper() == call]
        return matches[-count:]

    def who_spots_me(self, band: str, operator_call: str) -> list[str]:
        """Summarise the countries that have recently spotted ``operator_call``."""
        call = (operator_call or "").upper()
        if not call:
            return ["Set your callsign to use WHOSPOTSME."]
        band_key = band.lower() if band else ""
        counts: dict[str, dict[str, int]] = {}
        for spot, _ in self._history:
            if spot.dx_call.upper() != call:
                continue
            if band_key and spot.band.lower() != band_key:
                continue
            continent = spot.spotter_continent or "??"
            entity = spot.spotter_dxcc or spot.spotter or "??"
            counts.setdefault(continent, {})
            counts[continent][entity] = counts[continent].get(entity, 0) + 1
        label = band.upper() if band else "ALL"
        if not counts:
            return [f"WHOSPOTSME {label}: no recent reports of {call}."]
        lines = [f"WHOSPOTSME {label} (recent):"]
        for continent in sorted(counts):
            items = sorted(counts[continent].items(), key=lambda kv: (-kv[1], kv[0]))
            lines.append(f"  {continent}: " + " ".join(f"{k}({v})" for k, v in items))
        return lines

    def prop_outlook(self, target: str, band: str, mode: str) -> list[str]:
        """Return an hourly propagation outlook for ``target`` (call/prefix/grid)."""
        voacap = self.enricher.voacap
        if voacap is None:
            return ["Propagation engine disabled."]
        operator_grid = self.enricher.operator_grid
        if len(operator_grid) < 4:
            return ["Set your grid with SET GRID first."]
        grid = self._resolve_target_grid(target)
        if not grid:
            return [f"Could not resolve {target!r} to a grid locator."]

        band_key = (band.lower() if band else "20m")
        if band_key.isdigit():
            band_key += "m"
        if band_key not in BAND_FREQ_INDEX:
            return [f"No propagation model for band {band_key!r}."]
        mode_key = (mode or "CW").upper()
        freq_khz = FREQS_MHZ[BAND_FREQ_INDEX[band_key]] * 1000.0

        now = datetime.now(UTC)
        header = (
            f"PROP {operator_grid} -> {grid} band={band_key} mode={mode_key} ssn={voacap.ssn}"
        )
        rows: list[str] = []
        for hour in range(24):
            when = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            path = voacap.predict(grid, band_key, freq_khz, mode_key, when)
            if path in (PathClass.HIGH, PathClass.MEDIUM, PathClass.LOW):
                rows.append(f"{hour:02d}Z  {PATH_SYMBOL[path]}  {path.value}")
        if not rows:
            return [header, "No HIGH/MEDIUM/LOW rows in the forecast window."]
        return [header, *rows]

    def _resolve_target_grid(self, target: str) -> str:
        candidate = target.strip().upper()
        if _GRID_RE.match(candidate):
            return candidate
        entity = self.validator.cty.lookup(target)
        return entity.grid if entity is not None else ""

    def close(self) -> None:
        pass