from rxcluster.bus.pubsub import SpotBus, Subscriber
from rxcluster.dedup.window import DedupWindow
from rxcluster.filters.compiled import compile_filter
from rxcluster.filters.model import FilterState
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


def _subscriber(name: str, window: float) -> Subscriber:
    return Subscriber(
        name,
        compile_filter(FilterState(), name),
        dedup_window_seconds=window,
        freq_tolerance_khz=0.1,
    )


def test_per_subscriber_dedup_counts_suppressed():
    bus = SpotBus()
    bus.subscribe(_subscriber("FAST", 10.0))
    bus.subscribe(_subscriber("SLOW", 60.0))
    spot = make_spot()
    assert bus.publish(spot, "line") == (2, 0)
    # Both subscribers suppress the immediate repeat, each counted.
    assert bus.publish(spot, "line") == (0, 2)


def test_zero_window_disables_dedup():
    bus = SpotBus()
    sub = _subscriber("X", 0.0)
    bus.subscribe(sub)
    assert not sub.is_duplicate(make_spot())
    assert bus.publish(make_spot(), "line") == (1, 0)
    assert bus.publish(make_spot(), "line") == (1, 0)


def test_filtered_out_spot_does_not_enter_window():
    bus = SpotBus()
    sub = _subscriber("X", 30.0)
    bus.subscribe(sub)
    sub.filter = compile_filter(FilterState(reject={"band": {"40m"}}), "X")
    spot = make_spot()
    spot.band = "40m"
    assert bus.publish(spot, "line") == (0, 0)  # filtered out, not a duplicate
    sub.filter = compile_filter(FilterState(), "X")
    # The first allowed delivery must not be treated as a duplicate.
    assert bus.publish(spot, "line") == (1, 0)


def test_set_dedup_window_reconfigures():
    sub = _subscriber("X", 0.0)
    assert sub.dedup_window_seconds == 0.0
    sub.set_dedup_window(30.0)
    assert sub.dedup_window_seconds == 30.0
    assert not sub.is_duplicate(make_spot())
    assert sub.is_duplicate(make_spot())