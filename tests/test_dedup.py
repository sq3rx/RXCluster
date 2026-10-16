from rxcluster.dedup.window import DedupWindow
from rxcluster.models import Source, SourceType, Spot


def make_spot(spotter="W3LPL", call="K1ABC", freq=7005.0) -> Spot:
    return Spot(
        source=Source.RBN,
        source_type=SourceType.SKIMMER,
        spotter=spotter,
        dx_call=call,
        freq_khz=freq,
        timestamp=0.0,
    )


def test_duplicate_detection():
    window = DedupWindow(window_seconds=30.0, freq_tolerance_khz=0.1)
    assert not window.is_duplicate(make_spot(), now=100.0)
    assert window.is_duplicate(make_spot(), now=101.0)
    # Different spotter is not a duplicate.
    assert not window.is_duplicate(make_spot(spotter="DL1ABC"), now=101.0)


def test_window_expiry():
    window = DedupWindow(window_seconds=10.0)
    assert not window.is_duplicate(make_spot(), now=0.0)
    assert window.is_duplicate(make_spot(), now=5.0)
    # A fully new observation after the window is placed with the same ts key.
    assert not window.is_duplicate(make_spot(), now=100.0)