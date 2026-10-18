from rxcluster.config import ValidationConfig
from rxcluster.filters.compiled import compile_filter
from rxcluster.filters.model import FilterState
from rxcluster.filters.parser import parse_command
from rxcluster.models import Confidence, Source, SourceType, Spot
from rxcluster.validate.corroboration import Corroborator, levenshtein
from rxcluster.validate.cty import CtyDatabase
from rxcluster.validate.patterns import base_call, is_valid_shape
from rxcluster.validate.scp import ScpDatabase
from rxcluster.validate.validator import Validator


def make_spot(call="K1ABC", spotter="W3LPR", freq=7005.0) -> Spot:
    return Spot(
        source=Source.RBN,
        source_type=SourceType.SKIMMER,
        spotter=spotter,
        dx_call=call,
        freq_khz=freq,
        timestamp=0.0,
    )


def test_base_call_and_shape():
    assert base_call("VP2E/P") == "VP2E"
    assert base_call("3D2/R") == "3D2"
    assert is_valid_shape("K1ABC")
    assert not is_valid_shape("ABC")  # no digit
    assert not is_valid_shape("AAAA1")  # repeated chars


def test_levenshtein():
    assert levenshtein("K1ABC", "K1ABC") == 0
    assert levenshtein("K1ABC", "K1ABD") == 1
    assert levenshtein("K1ABC", "K1ABDE") <= 2


def test_validator_accepts_scp_call():
    scp = ScpDatabase()
    scp.load_lines(["K1ABC"])
    validator = Validator(ValidationConfig(), scp, CtyDatabase())
    spot = make_spot("K1ABC")
    assert validator.process(spot)
    assert spot.confidence in (Confidence.STATIC, Confidence.VALID)


def test_validator_rejects_bad_shape():
    validator = Validator(ValidationConfig(), ScpDatabase(), CtyDatabase())
    assert not validator.process(make_spot("XXX"))


def test_corroboration_valid():
    scp = ScpDatabase()
    validator = Validator(ValidationConfig(), scp, CtyDatabase())
    for spotter in ("W1AAA", "W2BBB", "W3CCC"):
        spot = make_spot("DL1ABC", spotter=spotter)
        validator.process(spot)
    assert spot.confidence is Confidence.VALID


def test_busted_detection():
    scp = ScpDatabase()
    validator = Validator(ValidationConfig(), scp, CtyDatabase())
    # Establish a well-supported call.
    for spotter in ("W1AAA", "W2BBB"):
        validator.process(make_spot("K1ABC", spotter=spotter))
    # A nearby, unsupported variant is flagged as busted but still forwarded.
    bust = make_spot("K1ABD", spotter="W9XYZ")
    assert validator.process(bust)
    assert bust.confidence is Confidence.BUST
    assert bust.dx_call == "K1ABD"
    assert "bust? K1ABC" in bust.comment


def test_corrected_detection():
    scp = ScpDatabase()
    scp.load_lines(["K1ABC"])
    validator = Validator(ValidationConfig(), scp, CtyDatabase())
    for spotter in ("W1AAA", "W2BBB"):
        validator.process(make_spot("K1ABC", spotter=spotter))
    # A nearby variant is corrected to the known-good SCP call and tagged C.
    spot = make_spot("K1ABD", spotter="W9XYZ")
    assert validator.process(spot)
    assert spot.confidence is Confidence.CORRECTED
    assert spot.dx_call == "K1ABC"
    assert spot.comment == "ex K1ABD"


def test_corroborator_prunes_stale_buckets():
    corr = Corroborator(window_seconds=120.0)
    for i in range(50):
        corr.evaluate(make_spot("K1ABC", freq=7000.0 + i), now=0.0)
    assert len(corr._by_freq) == 50
    # After the window elapses, a new spot triggers a full sweep of stale data.
    corr.evaluate(make_spot("K1ABC", freq=30000.0), now=1000.0)
    assert len(corr._by_freq) == 1


_CTY = (
    "United States:            05:  08:  NA:   37.60:    91.87:     5.0:  K:\n"
    "    AA,AB,AK,K,N,W,=4U1WB(5)[8],=AA0BY(3)[6];\n"
    "Poland:                   15:  28:  EU:   52.28:   -18.67:    -1.0:  SP:\n"
    "    3Z,HF,SN,SO,SP,SQ,SR;\n"
)


def _load_cty(tmp_path):
    path = tmp_path / "cty.dat"
    path.write_text(_CTY, encoding="utf-8")
    cty = CtyDatabase()
    cty.load(str(path))
    return cty


def test_cty_continuation_prefixes(tmp_path):
    cty = _load_cty(tmp_path)
    # Prefixes from continuation lines (W, SQ, ...) must resolve, not just the
    # header's primary prefix (K, SP).
    assert cty.lookup("W3LPR").continent == "NA"
    assert cty.lookup("N0CALL").continent == "NA"
    assert cty.lookup("4U1WB").continent == "NA"  # '=' override prefix
    assert cty.lookup("SQ9ABC").continent == "EU"


def test_cty_tolerates_blank_lines(tmp_path):
    # CR-CR-LF line endings inject a blank line after every line; the
    # continuation prefixes must still be attributed to the right entity.
    path = tmp_path / "cty.dat"
    path.write_bytes(_CTY.replace("\n", "\r\r\n").encode("utf-8"))
    cty = CtyDatabase()
    cty.load(str(path))
    assert cty.lookup("W3LPR").continent == "NA"
    assert cty.lookup("SQ9ABC").continent == "EU"


def test_dxcont_decont_filters_after_geography(tmp_path):
    cty = _load_cty(tmp_path)
    validator = Validator(ValidationConfig(), ScpDatabase(), cty)

    spot = make_spot("SQ9ABC", spotter="W3LPR")
    validator.process(spot)
    assert spot.continent == "EU"
    assert spot.spotter_continent == "NA"

    state = FilterState()
    parse_command("REJECT DXCONT ALL", state)
    parse_command("PASS DXCONT EU", state)
    assert compile_filter(state).allows(spot)  # DX is EU

    state = FilterState()
    parse_command("REJECT DECONT ALL", state)
    parse_command("PASS DECONT EU", state)
    assert not compile_filter(state).allows(spot)  # spotter is NA


def test_dxdxcc_prefix_resolved_via_cty(tmp_path):
    cty = _load_cty(tmp_path)
    validator = Validator(ValidationConfig(), ScpDatabase(), cty)
    spot = make_spot("SQ9ABC", spotter="W3LPR")
    validator.process(spot)

    # SP is a Poland prefix; the spot's call SQ9ABC also resolves to Poland.
    state = FilterState()
    parse_command("REJECT DXDXCC SP", state)
    assert not compile_filter(state, cty=cty).allows(spot)
    # Without cty only the literal value / call prefix is compared.
    assert compile_filter(state, cty=None).allows(spot)

    # DEDXCC resolves the spotter's entity the same way.
    state = FilterState()
    parse_command("REJECT DEDXCC W", state)
    assert not compile_filter(state, cty=cty).allows(spot)
