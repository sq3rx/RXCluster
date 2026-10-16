from rxcluster.filters.compiled import compile_filter, describe
from rxcluster.filters.model import FilterState
from rxcluster.filters.parser import CommandHandlers, parse_command
from rxcluster.models import Confidence, Mode, Source, SourceType, Spot


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
    state = FilterState()
    parse_command("PASS NEARBY ON", state, CommandHandlers(operator_grid="FN31"))
    assert state.nearby is True
    compiled = compile_filter(state, "N0CALL", "FN31")
    assert compiled.allows(make_spot(dx_grid="FN42"))
    assert not compiled.allows(make_spot(dx_grid="JO90"))

    parse_command("PASS NEARBY OFF", state)
    assert state.nearby is False


def test_nearby_without_grid_warns():
    state = FilterState()
    result = parse_command("PASS NEARBY ON", state, CommandHandlers(operator_grid=""))
    assert "SET GRID" in result.responses[0]


def test_describe_category_and_full():
    state = FilterState()
    assert "BAND" in describe(state, "band")
    assert "SWITCHES" in describe(state, full=True)
