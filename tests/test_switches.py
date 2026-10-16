from rxcluster.filters.compiled import compile_filter
from rxcluster.filters.model import FilterState
from rxcluster.filters.parser import parse_command
from rxcluster.models import Confidence, Mode, Source, SourceType, Spot, SpotKind


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


def test_beacon_switch_toggles():
    state = FilterState()
    assert not compile_filter(state).allows(make_spot(is_beacon=True, kind=SpotKind.BEACON))
    parse_command("PASS BEACON", state)
    assert state.switches["beacon"] is True
    assert compile_filter(state).allows(make_spot(is_beacon=True, kind=SpotKind.BEACON))
    parse_command("REJECT BEACON", state)
    assert not compile_filter(state).allows(make_spot(is_beacon=True, kind=SpotKind.BEACON))


def test_bulletin_switches():
    state = FilterState()
    # WWV/WCY/ANNOUNCE default on.
    assert compile_filter(state).allows(make_spot(kind=SpotKind.WWV))
    assert compile_filter(state).allows(make_spot(kind=SpotKind.WCY))
    assert compile_filter(state).allows(make_spot(kind=SpotKind.ANNOUNCE))

    parse_command("REJECT WWV", state)
    assert not compile_filter(state).allows(make_spot(kind=SpotKind.WWV))
    parse_command("REJECT ANNOUNCE", state)
    assert not compile_filter(state).allows(make_spot(kind=SpotKind.ANNOUNCE))
    # WCY untouched.
    assert compile_filter(state).allows(make_spot(kind=SpotKind.WCY))


def test_toxic_switch():
    state = FilterState()
    parse_command("PASS TOXIC", state)
    assert compile_filter(state).allows(make_spot(toxic=True))
    parse_command("REJECT TOXIC", state)
    assert not compile_filter(state).allows(make_spot(toxic=True))


def test_self_switch():
    state = FilterState()
    # Self spots are hidden by default.
    assert not compile_filter(state, "K1ABC").allows(make_spot(dx_call="K1ABC"))
    parse_command("PASS SELF", state)
    assert compile_filter(state, "K1ABC").allows(make_spot(dx_call="K1ABC"))
