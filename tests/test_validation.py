from rxcluster.config import ValidationConfig
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