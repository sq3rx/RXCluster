"""Enrichment stage: propagation prediction and output rendering."""

from __future__ import annotations

from ..config import EnrichmentConfig
from ..models import Spot, SpotKind
from .tags import render_bulletin, render_line
from .voacap.engine import VoacapEngine


class Enricher:
    def __init__(self, cfg: EnrichmentConfig, operator_grid: str) -> None:
        self.cfg = cfg
        self.operator_grid = operator_grid
        self.voacap = VoacapEngine(cfg.voacap, operator_grid) if cfg.voacap.enabled else None

    def process(self, spot: Spot) -> None:
        """Set the propagation path class for ``spot`` in place."""
        if self.voacap is None:
            return
        if not spot.dx_grid:
            return
        spot.path = self.voacap.predict(
            target_grid=spot.dx_grid,
            band=spot.band,
            freq_khz=spot.freq_khz,
            mode=spot.mode.value,
        )

    async def refresh_solar(self) -> None:
        if self.voacap is not None:
            await self.voacap.refresh_solar()

    async def precompute(self) -> None:
        if self.voacap is not None:
            await self.voacap.precompute()

    def render(self, spot: Spot, width: int = 76) -> str:
        if spot.kind in (SpotKind.WWV, SpotKind.WCY, SpotKind.ANNOUNCE):
            return render_bulletin(spot, width)
        return render_line(spot, self.cfg.tags, width)