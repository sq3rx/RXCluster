"""Validation and geography resolution stage.

Combines shape checking, SCP membership, cty.dat lookup and cross-source
corroboration. Clearly malformed callsigns and detected busted spots are
rejected; all accepted spots receive a confidence tag and geography metadata.
"""

from __future__ import annotations

from ..config import ValidationConfig
from ..models import Confidence, Spot
from .corroboration import Corroborator
from .cty import CtyDatabase
from .patterns import base_call, is_valid_shape
from .scp import ScpDatabase


class Validator:
    def __init__(
        self,
        cfg: ValidationConfig,
        scp: ScpDatabase,
        cty: CtyDatabase,
    ) -> None:
        self.cfg = cfg
        self.scp = scp
        self.cty = cty
        corr = cfg.corroboration
        self.corroborator = Corroborator(
            window_seconds=corr.window_seconds,
            min_agree=corr.min_agree,
            edit_distance=corr.edit_distance,
        )

    def process(self, spot: Spot) -> bool:
        """Validate ``spot`` in place. Returns ``True`` if it should be kept."""
        if self.cfg.cty_enabled:
            self._resolve_geography(spot)

        base = base_call(spot.dx_call)
        if not is_valid_shape(base):
            return False

        in_scp: bool | None = None
        if self.cfg.scp_enabled and self.scp.loaded:
            in_scp = self.scp.contains(base)

        if self.cfg.corroboration.enabled:
            result = self.corroborator.evaluate(spot, in_scp)
            if result.confidence is Confidence.BUST and result.suggested_call:
                self._apply_correction(spot, result.suggested_call)
            else:
                spot.confidence = result.confidence
        else:
            spot.confidence = Confidence.STATIC if in_scp else Confidence.LOW
        return True

    def _apply_correction(self, spot: Spot, suggestion: str) -> None:
        """Tag a suspected bust as ``C`` (corrected) or ``B`` (busted).

        When the suggested call is a known-good SCP entry the spot is
        corrected in place and tagged ``C``; otherwise it is kept with its
        original call and tagged ``B`` so the operator can see the suspect.
        """
        if self.cfg.scp_enabled and self.scp.loaded and self.scp.contains(suggestion):
            original = base_call(spot.dx_call)
            spot.dx_call = suggestion.upper()
            spot.confidence = Confidence.CORRECTED
            if self.cfg.cty_enabled:
                self._resolve_geography(spot)
            if not spot.comment:
                spot.comment = f"ex {original}"
            return
        spot.confidence = Confidence.BUST
        if not spot.comment:
            spot.comment = f"bust? {suggestion}"

    def _resolve_geography(self, spot: Spot) -> None:
        dx_entity = self.cty.lookup(spot.dx_call)
        if dx_entity is not None:
            spot.dxcc = dx_entity.name
            spot.continent = dx_entity.continent
            spot.cq_zone = dx_entity.cq_zone
            if not spot.dx_grid:
                spot.dx_grid = dx_entity.grid
        de_entity = self.cty.lookup(spot.spotter)
        if de_entity is not None:
            spot.spotter_dxcc = de_entity.name
            spot.spotter_continent = de_entity.continent
            spot.spotter_cq_zone = de_entity.cq_zone
            if not spot.spotter_grid:
                spot.spotter_grid = de_entity.grid