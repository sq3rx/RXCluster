from rxcluster.models import Mode
from rxcluster.parse.freq import BandPlan

RANGES = [
    (1800, 2000, "160m"),
    (3500, 4000, "80m"),
    (7000, 7300, "40m"),
    (14000, 14350, "20m"),
]
SUB = {
    "80m": {"cw_high": 3600, "ssb_low": 3600},
    "40m": {"cw_high": 7040, "ssb_low": 7040},
    "20m": {"cw_high": 14070, "ssb_low": 14100},
}


def test_band_lookup():
    plan = BandPlan(RANGES, SUB)
    assert plan.band_for_freq(7005) == "40m"
    assert plan.band_for_freq(14200) == "20m"
    assert plan.band_for_freq(2050) == ""
    assert plan.band_for_freq(50000) == ""


def test_mode_inference():
    plan = BandPlan(RANGES, SUB)
    assert plan.infer_mode(7020, "40m") is Mode.CW
    assert plan.infer_mode(7120, "40m") is Mode.SSB
    assert plan.infer_mode(14080, "20m") is Mode.UNKNOWN
    assert plan.infer_mode(14100, "20m", explicit=Mode.RTTY) is Mode.RTTY