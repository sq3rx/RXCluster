"""Session-level NEARBY (proximity) filtering.

NEARBY is a per-session feature rather than a filter category: it depends on
the operator's own grid locator, not on the PASS/REJECT selections. It is kept
out of the (interned, shared) :class:`~rxcluster.filters.compiled.CompiledFilter`
so the compiled filter stays a pure function of the filter state.

A spot passes NEARBY when either its DX grid or its spotter grid is within the
configured radius. The radius is wider on the low bands.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..grid import distance_km, grid_to_latlon
from ..models import Spot

DEFAULT_RADIUS_KM = 700.0
DEFAULT_LOW_BAND_RADIUS_KM = 1500.0
DEFAULT_LOW_BANDS: tuple[str, ...] = ("160m", "80m", "60m")


@dataclass
class NearbySpec:
    """Mutable per-session NEARBY configuration."""

    enabled: bool = False
    radius_km: float = DEFAULT_RADIUS_KM
    low_band_radius_km: float = DEFAULT_LOW_BAND_RADIUS_KM
    low_bands: tuple[str, ...] = DEFAULT_LOW_BANDS

    @classmethod
    def from_config(cls, cfg) -> NearbySpec:
        """Build a spec from a :class:`~rxcluster.config.NearbyConfig`."""
        return cls(
            radius_km=float(cfg.radius_km),
            low_band_radius_km=float(cfg.low_band_radius_km),
            low_bands=tuple(cfg.low_bands),
        )


class NearbyFilter:
    """Immutable proximity predicate for one session.

    ``enabled`` is only effective when the operator grid resolves to a valid
    locator; otherwise the filter stays inert (it never removes a spot).
    """

    __slots__ = ("_spec", "_pos", "_low_bands", "_operator", "_bypass_own")

    def __init__(
        self,
        operator_grid: str,
        spec: NearbySpec,
        operator_call: str = "",
        bypass_own: bool = False,
    ) -> None:
        self._spec = spec
        self._low_bands = frozenset(spec.low_bands)
        grid = operator_grid.strip().upper()
        self._pos = grid_to_latlon(grid) if grid else None
        self._operator = operator_call.strip().upper()
        self._bypass_own = bool(bypass_own)

    @property
    def enabled(self) -> bool:
        """Whether NEARBY is active (on and with a usable operator grid)."""
        return self._spec.enabled and self._pos is not None

    def allows(self, spot: Spot) -> bool:
        if not self.enabled:
            return True
        # An operator's own call stays visible when SELF is on, regardless of
        # distance (mirrors the SELF bypass).
        if self._bypass_own and self._operator and spot.dx_call.upper() == self._operator:
            return True
        radius = (
            self._spec.low_band_radius_km
            if spot.band in self._low_bands
            else self._spec.radius_km
        )
        op_lat, op_lon = self._pos
        for grid in (spot.dx_grid, spot.spotter_grid):
            target = grid_to_latlon(grid) if grid else None
            if target is None:
                continue
            if distance_km(op_lat, op_lon, target[0], target[1]) <= radius:
                return True
        return False
