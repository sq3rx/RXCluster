from rxcluster.filters.compiled import compile_filter, describe
from rxcluster.filters.model import FilterState
from rxcluster.filters.parser import parse_command
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


def test_band_reject():
    state = FilterState()
    parse_command("REJECT BAND 20", state)
    compiled = compile_filter(state)
    assert compiled.allows(make_spot(band="40m"))
    assert not compiled.allows(make_spot(band="20m"))


def test_band_only_selection():
    state = FilterState()
    parse_command("REJECT BAND ALL", state)
    parse_command("PASS BAND 20,40", state)
    compiled = compile_filter(state)
    assert compiled.allows(make_spot(band="40m"))
    assert compiled.allows(make_spot(band="20m"))
    assert not compiled.allows(make_spot(band="80m"))


def test_mode_preserve_semantics():
    state = FilterState()
    parse_command("PASS MODE CW", state)
    compiled = compile_filter(state)
    # Other modes remain visible.
    assert compiled.allows(make_spot(mode=Mode.FT8))
    parse_command("REJECT MODE FT8", state)
    compiled = compile_filter(state)
    assert not compiled.allows(make_spot(mode=Mode.FT8))


def test_minsnr():
    state = FilterState()
    parse_command("PASS MINSNR CW 10", state)
    compiled = compile_filter(state)
    assert compiled.allows(make_spot(snr=15, mode=Mode.CW))
    assert not compiled.allows(make_spot(snr=5, mode=Mode.CW))
    # Human reports are exempt.
    assert compiled.allows(make_spot(snr=5, mode=Mode.CW, source_type=SourceType.HUMAN))


def test_comment_filters():
    state = FilterState()
    parse_command("REJECT COMMENT QRT", state)
    compiled = compile_filter(state)
    assert not compiled.allows(make_spot(comment="please QRT"))
    assert compiled.allows(make_spot(comment="cq test"))


def test_call_pattern():
    state = FilterState()
    parse_command("REJECT DECALL W3L*", state)
    compiled = compile_filter(state)
    assert not compiled.allows(make_spot(spotter="W3LPR"))
    assert compiled.allows(make_spot(spotter="DL1ABC"))


def test_call_pattern_whitelist_and_all():
    state = FilterState()
    parse_command("REJECT DXCALL ALL", state)
    parse_command("PASS DXCALL K1*", state)
    compiled = compile_filter(state)
    assert compiled.allows(make_spot(dx_call="K1ABC"))
    assert not compiled.allows(make_spot(dx_call="DL1ABC"))

    parse_command("PASS DXCALL ALL", state)
    compiled = compile_filter(state)
    assert compiled.allows(make_spot(dx_call="DL1ABC"))


def test_confidence_reject():
    state = FilterState()
    parse_command("REJECT CONFIDENCE ?", state)
    compiled = compile_filter(state)
    assert not compiled.allows(make_spot(confidence=Confidence.LOW))
    assert compiled.allows(make_spot(confidence=Confidence.VALID))


def test_describe_runs():
    state = FilterState()
    assert "BAND" in describe(state)


def test_event_reject_and_whitelist():
    state = FilterState()
    parse_command("REJECT EVENT POTA", state)
    compiled = compile_filter(state)
    assert not compiled.allows(make_spot(comment="POTA activation"))
    assert compiled.allows(make_spot(comment="plain report"))

    state = FilterState()
    parse_command("REJECT EVENT ALL", state)
    parse_command("PASS EVENT SOTA", state)
    compiled = compile_filter(state)
    assert compiled.allows(make_spot(comment="SOTA summit"))
    assert compiled.allows(make_spot(comment="plain"))  # untagged always passes
    assert not compiled.allows(make_spot(comment="POTA activation"))


def test_dxdxcc_multiword_entity():
    state = FilterState()
    parse_command("REJECT DXDXCC United States", state)
    compiled = compile_filter(state)
    assert not compiled.allows(make_spot(dxcc="United States"))
    assert compiled.allows(make_spot(dxcc="Germany"))


def test_comment_multiword_phrases():
    state = FilterState()
    parse_command("REJECT COMMENT QRT,test me", state)
    compiled = compile_filter(state)
    assert not compiled.allows(make_spot(comment="please QRT now"))
    assert not compiled.allows(make_spot(comment="test me"))
    assert compiled.allows(make_spot(comment="cq contest"))


def test_reject_minsnr_clears_threshold():
    state = FilterState()
    parse_command("PASS MINSNR CW 10", state)
    assert state.min_snr == {"CW": 10}
    parse_command("REJECT MINSNR CW", state)
    assert state.min_snr == {}