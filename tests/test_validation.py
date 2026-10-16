from rxcluster.config import ValidationConfig
from rxcluster.models import Confidence, Source, SourceType, Spot
from rxcluster.validate.corroboration import levenshtein
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
    # A nearby, unsupported variant should be flagged as busted and rejected.
    bust = make_spot("K1ABD", spotter="W9XYZ")
    assert not validator.process(bust)
    assert bust.confidence is Confidence.BUST