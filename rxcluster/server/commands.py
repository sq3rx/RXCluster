"""Command execution bound to a client session."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from ..bus.pubsub import Subscriber
from ..config import Config
from ..filters.compiled import CompiledFilter, compile_filter
from ..filters.model import FilterState, default_state_from_config
from ..filters.nearby import NearbyFilter, NearbySpec
from ..filters.parser import (
    CommandHandlers,
    CommandResult,
    PostRequest,
    parse_command,
)
from ..grid import is_valid_grid
from ..pipeline import Pipeline
from ..validate.cty import CtyDatabase


@dataclass(eq=False)
class ClientSession:
    callsign: str
    state: FilterState
    compiled: CompiledFilter
    subscriber: Subscriber
    grid: str = ""
    noise: str = "SUBURBAN"
    dedupe_policy: str = "SLOW"
    paused_until: float = 0.0
    suppressed: int = 0
    cty: CtyDatabase | None = None
    nearby: NearbySpec = field(default_factory=NearbySpec)
    persist: Callable[[], None] | None = field(default=None, repr=False, compare=False)

    def recompile(self) -> None:
        self.compiled = compile_filter(self.state, self.callsign, self.cty)
        self.subscriber.filter = self.compiled
        self.subscriber.nearby = NearbyFilter(
            self.grid,
            self.nearby,
            operator_call=self.callsign,
            bypass_own=self.state.switches.get("self", False),
        )


def execute_command(
    line: str, session: ClientSession, cfg: Config, pipeline: Pipeline
) -> CommandResult:
    def _set_grid(grid: str) -> None:
        session.grid = grid

    def _set_noise(noise: str) -> None:
        session.noise = noise

    def _set_dedupe(policy: str) -> None:
        session.dedupe_policy = policy
        dedup_cfg = cfg.pipeline.dedup
        session.subscriber.set_dedup_window(
            dedup_cfg.window_for(policy), dedup_cfg.freq_tolerance_khz
        )

    def _set_nearby(enabled: bool, radius: float | None, low_radius: float | None) -> str:
        session.nearby.enabled = enabled
        if radius is not None:
            session.nearby.radius_km = radius
        if low_radius is not None:
            session.nearby.low_band_radius_km = low_radius
        if not enabled:
            return "NEARBY off."
        if not is_valid_grid(session.grid):
            return "NEARBY on; set a grid with SET GRID for it to take effect."
        return (
            f"NEARBY on ({session.nearby.radius_km:g} km, "
            f"{session.nearby.low_band_radius_km:g} km on the low bands)."
        )

    def _nearby_info() -> list[str]:
        spec = session.nearby
        grid = session.grid or "not set"
        low = ",".join(spec.low_bands)
        lines = [
            f"NEARBY      {'on' if spec.enabled else 'off'}",
            f"GRID        {grid}",
            f"RADIUS      {spec.radius_km:g} km ({spec.low_band_radius_km:g} km on {low})",
        ]
        if spec.enabled and not is_valid_grid(session.grid):
            lines.append("note: NEARBY is inert until a valid grid is set (SET GRID).")
        return lines

    def _hold() -> str:
        remaining = session.paused_until - time.monotonic()
        if remaining > 0:
            return (
                f"Live spots paused; {int(remaining) + 1}s remaining, "
                f"{session.suppressed} spots suppressed."
            )
        return "Live spots are running."

    def _resume() -> str:
        session.paused_until = 0.0
        return "Live spots resumed."

    def _post(request: PostRequest) -> str:
        return pipeline.post_manual(session.callsign, request)

    handlers = CommandHandlers(
        operator_call=session.callsign,
        operator_grid=session.grid,
        recent_provider=pipeline.recent,
        recent_for_provider=pipeline.recent_for,
        grid_setter=_set_grid,
        noise_setter=_set_noise,
        dedupe_setter=_set_dedupe,
        dedupe_provider=lambda: session.dedupe_policy,
        prop_provider=pipeline.prop_outlook,
        whospotsme_provider=pipeline.who_spots_me,
        post_handler=_post,
        resume_setter=_resume,
        hold_provider=_hold,
        nearby_setter=_set_nearby,
        nearby_provider=_nearby_info,
        default_state_provider=lambda: default_state_from_config(cfg.defaults),
    )
    result = parse_command(line, session.state, handlers)
    if result.changed:
        session.recompile()
        if session.persist is not None:
            session.persist()
    return result
