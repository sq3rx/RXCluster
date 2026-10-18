from rxcluster.filters.compiled import compile_filter, describe
from rxcluster.filters.model import DEFAULT_SWITCHES, FilterState
from rxcluster.filters.nearby import NearbyFilter, NearbySpec
from rxcluster.filters.parser import CommandHandlers, parse_command
from rxcluster.grid import is_valid_grid
from rxcluster.models import Confidence, Mode, Source, SourceType, Spot


def _nearby_handlers(spec: NearbySpec, grid: str) -> CommandHandlers:
    """Wire the session-level NEARBY callbacks the telnet server provides."""

    def setter(enabled: bool, radius: float | None) -> str:
        spec.enabled = enabled
        if radius is not None:
            spec.radius_km = radius
        if not enabled:
            return "NEARBY off."
        if not is_valid_grid(grid):
            return "NEARBY on; set a grid with SET GRID for it to take effect."
        return f"NEARBY on ({spec.radius_km:g} km)."

    return CommandHandlers(operator_grid=grid, nearby_setter=setter)


def make_spot(**kwargs) -> Spot:
    base = dict(
        source=Source.RBN,
        source_type=SourceType.SKIMMER,
        spotter="W3LPR",
        dx_call="K1ABC",
        freq_khz=7005.0,
        timestamp=0.0,
        band="40m",
        mode=Mode.CW,
        continent="NA",
        confidence=Confidence.VALID,
    )
    base.update(kwargs)
    return Spot(**base)


def test_unknown_command_hint():
    result = parse_command("FROBNICATE", FilterState())
    assert result.handled
    assert "Unknown command" in result.responses[0]


def test_help_topic():
    result = parse_command("HELP DX", FilterState())
    assert "Post a spot" in result.responses[0]
    generic = parse_command("HELP", FilterState())
    assert "RXCluster help" in generic.responses[0]


def test_show_filter_full_and_category():
    state = FilterState()
    parse_command("PASS BAND 20", state)
    full = parse_command("SHOW FILTER FULL", state)
    assert "SWITCHES" in full.responses[0]
    assert full.pause_seconds > 0
    band = parse_command("SHOW FILTER BAND", state)
    assert band.responses[0].startswith("BAND")


def test_pause_resume_hold():
    state = FilterState()
    paused = parse_command("PAUSE 60", state)
    assert paused.pause_seconds == 60.0
    resumed = parse_command(
        "RESUME", state, CommandHandlers(resume_setter=lambda: "Live spots resumed.")
    )
    assert resumed.responses == ["Live spots resumed."]
    hold = parse_command(
        "SHOW HOLD", state, CommandHandlers(hold_provider=lambda: "Live spots are running.")
    )
    assert hold.responses == ["Live spots are running."]


def test_show_prop_requires_handler():
    result = parse_command("SHOW PROP K1ABC 20m CW", FilterState())
    assert "unavailable" in result.responses[0]


def test_whospotsme_handler():
    calls: dict[str, str] = {}

    def provider(band: str, call: str) -> list[str]:
        calls["band"] = band
        calls["call"] = call
        return ["WHOSPOTSME 20M (recent):", "  EU: DL(2)"]

    result = parse_command(
        "WHOSPOTSME 20M",
        FilterState(),
        CommandHandlers(operator_call="K1ABC", whospotsme_provider=provider),
    )
    assert calls == {"band": "20M", "call": "K1ABC"}
    assert result.responses[1] == "  EU: DL(2)"


def test_dxgrid2_filter():
    state = FilterState()
    parse_command("REJECT DXGRID2 JO", state)
    compiled = compile_filter(state)
    assert compiled.allows(make_spot(dx_grid="FN31"))
    assert not compiled.allows(make_spot(dx_grid="JO90"))


def test_degrid2_filter():
    state = FilterState()
    parse_command("REJECT DEGRID2 ALL", state)
    parse_command("PASS DEGRID2 FN", state)
    compiled = compile_filter(state)
    assert compiled.allows(make_spot(spotter_grid="FN20"))
    assert not compiled.allows(make_spot(spotter_grid="JO90"))


def test_dxcc_prefix_and_name():
    state = FilterState()
    parse_command("REJECT DXDXCC DL", state)
    compiled = compile_filter(state)
    assert not compiled.allows(make_spot(dx_call="DL1ABC", dxcc="Germany"))
    assert compiled.allows(make_spot(dx_call="K1ABC", dxcc="United States"))

    state2 = FilterState()
    parse_command("REJECT DXDXCC ALL", state2)
    parse_command("PASS DXDXCC germany", state2)
    compiled2 = compile_filter(state2)
    assert compiled2.allows(make_spot(dx_call="DL1ABC", dxcc="Germany"))
    assert not compiled2.allows(make_spot(dx_call="K1ABC", dxcc="United States"))


def test_nearby_filter():
    spec = NearbySpec()
    handlers = _nearby_handlers(spec, "FN31")
    parse_command("PASS NEARBY ON", FilterState(), handlers)
    assert spec.enabled is True
    nearby = NearbyFilter("FN31", spec)
    assert nearby.allows(make_spot(dx_grid="FN42"))
    assert not nearby.allows(make_spot(dx_grid="JO90"))

    parse_command("PASS NEARBY OFF", FilterState(), handlers)
    assert spec.enabled is False


def test_nearby_radius_argument():
    spec = NearbySpec()
    handlers = _nearby_handlers(spec, "FN31")
    parse_command("PASS NEARBY 300", FilterState(), handlers)
    assert spec.enabled is True
    assert spec.radius_km == 300.0


def test_nearby_without_grid_warns():
    spec = NearbySpec()
    result = parse_command("PASS NEARBY ON", FilterState(), _nearby_handlers(spec, ""))
    assert "SET GRID" in result.responses[0]


def test_nearby_without_grid_is_inert():
    nearby = NearbyFilter("", NearbySpec(enabled=True))
    assert nearby.allows(make_spot(dx_grid="JO90"))
    assert nearby.allows(make_spot())


def test_nearby_with_invalid_grid_is_inert():
    nearby = NearbyFilter("FOOBAR", NearbySpec(enabled=True))
    assert nearby.allows(make_spot(dx_grid="JO90"))


def test_nearby_low_band_uses_wider_radius():
    spec = NearbySpec(enabled=True, radius_km=100.0, low_band_radius_km=2000.0)
    nearby = NearbyFilter("FN31", spec, "N0CALL")
    # FN42 is a few hundred km away: out of range on 20m, inside on 80m.
    assert not nearby.allows(make_spot(dx_grid="FN42", band="20m"))
    assert nearby.allows(make_spot(dx_grid="FN42", band="80m"))


def test_set_grid_rejects_invalid_locator():
    captures: list[str] = []
    result = parse_command(
        "SET GRID FOOBAR", FilterState(), CommandHandlers(grid_setter=captures.append)
    )
    assert not result.changed
    assert "Invalid Maidenhead locator" in result.responses[0]
    assert captures == []


def test_set_grid_accepts_valid_locator():
    captures: list[str] = []
    result = parse_command(
        "SET GRID jo90aa", FilterState(), CommandHandlers(grid_setter=captures.append)
    )
    assert result.changed
    assert captures == ["JO90AA"]


def test_reject_nearby_disables():
    spec = NearbySpec(enabled=True)
    handlers = _nearby_handlers(spec, "FN31")
    parse_command("REJECT NEARBY", FilterState(), handlers)
    assert spec.enabled is False


def test_pass_nearby_false_disables():
    spec = NearbySpec(enabled=True)
    result = parse_command("PASS NEARBY FALSE", FilterState(), _nearby_handlers(spec, "FN31"))
    assert spec.enabled is False
    assert "off" in result.responses[0]


def test_self_on_own_call_bypasses_nearby():
    state = FilterState()
    parse_command("PASS SELF", state)
    nearby = NearbyFilter(
        "FN31", NearbySpec(enabled=True), operator_call="K1ABC", bypass_own=state.switches["self"]
    )
    assert nearby.allows(make_spot(dx_call="K1ABC", dx_grid="JO90"))
    assert nearby.allows(make_spot(dx_call="K1ABC"))


def test_self_off_own_call_rejected():
    state = FilterState()
    parse_command("REJECT SELF", state)
    compiled = compile_filter(state, "K1ABC")
    assert not compiled.allows(make_spot(dx_call="K1ABC"))


def test_lone_pass_exact_category_hint():
    # A lone PASS on an unrestricted exact category is inert and must say so.
    state = FilterState()
    result = parse_command("PASS DXCONT EU", state)
    assert state.allow["dxcont"] is None
    assert "REJECT DXCONT ALL" in result.responses[0]


def test_continent_aliases():
    for cmd in ("PASS CONT EU", "ACCEPT/CONT EU"):
        state = FilterState()
        parse_command("REJECT DXCONT ALL", state)
        parse_command(cmd, state)
        assert state.allow["dxcont"] == {"eu"}
    state = FilterState()
    parse_command("REJECT/CONT EU", state)
    assert state.reject["dxcont"] == {"eu"}


def test_set_continent_aliases():
    state = FilterState()
    parse_command("REJECT DXCONT ALL", state)
    parse_command("SET/DXCONT EU", state)
    assert state.allow["dxcont"] == {"eu"}
    parse_command("SET/NOCONT", state)
    assert state.allow["dxcont"] == set()


def test_reset_category_clears_only_that_category():
    state = FilterState()
    parse_command("REJECT BAND 40m", state)
    parse_command("REJECT DXCONT EU", state)
    parse_command("RESET BAND", state)
    assert state.reject["band"] == set()
    assert state.reject["dxcont"] == {"eu"}


def test_reset_all_without_defaults_clears_everything():
    state = FilterState()
    spec = NearbySpec(enabled=True)
    handlers = _nearby_handlers(spec, "FN31")
    parse_command("REJECT BAND 40m", state)
    parse_command("REJECT DXCONT EU", state)
    parse_command("PASS MINSNR CW 10", state)
    parse_command("REJECT BEACON", state)
    parse_command("RESET", state, handlers)
    assert state.reject["band"] == set()
    assert state.reject["dxcont"] == set()
    assert state.min_snr == {}
    assert spec.enabled is False
    assert state.switches == DEFAULT_SWITCHES


def test_reset_restores_node_defaults():
    state = FilterState()
    parse_command("REJECT BAND 40m", state)

    def defaults() -> FilterState:
        node = FilterState()
        parse_command("REJECT BAND ALL", node)
        parse_command("PASS BAND 20,40", node)
        return node

    parse_command("RESET", state, CommandHandlers(default_state_provider=defaults))
    assert state.reject["band"] == set()
    assert state.allow["band"] == {"20m", "40m"}


def test_describe_category_and_full():
    state = FilterState()
    assert "BAND" in describe(state, "band")
    assert "SWITCHES" in describe(state, full=True)


class _StubPipeline:
    def recent(self, count):
        return []

    def recent_for(self, call, count):
        return []

    def prop_outlook(self, target, band, mode):
        return []

    def who_spots_me(self, band, call):
        return []

    def post_manual(self, callsign, request):
        return "n/a"


def test_session_nearby_via_execute_command():
    from rxcluster.bus.pubsub import Subscriber
    from rxcluster.config import Config
    from rxcluster.server.commands import ClientSession, execute_command

    cfg = Config()
    state = FilterState()
    subscriber = Subscriber("SQ9ABC", compile_filter(state, "SQ9ABC"))
    session = ClientSession(
        callsign="SQ9ABC",
        state=state,
        compiled=subscriber.filter,
        subscriber=subscriber,
        grid="JO90AA",
        nearby=NearbySpec.from_config(cfg.pipeline.nearby),
    )
    pipeline = _StubPipeline()

    execute_command("PASS NEARBY ON", session, cfg, pipeline)
    assert session.nearby.enabled is True
    assert subscriber.nearby is not None and subscriber.nearby.enabled is True

    result = execute_command("SHOW NEARBY", session, cfg, pipeline)
    assert any("NEARBY" in line for line in result.responses)

    execute_command("PASS NEARBY 500", session, cfg, pipeline)
    assert session.nearby.radius_km == 500.0

    execute_command("REJECT NEARBY", session, cfg, pipeline)
    assert session.nearby.enabled is False
