import orjson
import pytest

from rxcluster.config import PskReporterConfig
from rxcluster.models import Mode, Source, SourceType
from rxcluster.sources.pskreporter import PskReporterConnector, adif_mode


def _spot(record: dict):
    return PskReporterConnector._to_spot(orjson.dumps(record))


def test_full_record_mapping():
    record = {
        "sq": 30142870791,
        "f": 14075982,
        "md": "FT8",
        "rp": -6,
        "t": 1662407712,
        "sc": "IZ8VYU",
        "sl": "JN71gm13",
        "rc": "KG6NFJ",
        "rl": "EM79WP",
        "sa": 248,
        "ra": 291,
        "b": "20m",
    }
    spot = _spot(record)
    assert spot is not None
    assert spot.dx_call == "IZ8VYU"
    assert spot.spotter == "KG6NFJ"
    assert spot.source is Source.PSKREPORTER
    assert spot.source_type is SourceType.SKIMMER
    assert spot.freq_khz == pytest.approx(14075.982)
    assert spot.mode is Mode.FT8
    assert spot.snr == -6
    assert spot.timestamp == pytest.approx(1662407712)
    assert spot.dx_grid == "JN71GM13"
    assert spot.spotter_grid == "EM79WP"


def test_missing_receiver_falls_back_to_psk_reporter():
    spot = _spot({"sc": "DL1ABC", "f": 7074000, "t": 1662407712, "md": "FT8"})
    assert spot is not None
    assert spot.spotter == "PSKREPORTER"
    assert spot.spotter_grid == ""


def test_missing_sender_returns_none():
    assert _spot({"rc": "KG6NFJ", "f": 14074000, "t": 1}) is None


def test_non_positive_frequency_returns_none():
    assert _spot({"sc": "DL1ABC", "f": 0, "t": 1}) is None
    assert _spot({"sc": "DL1ABC", "t": 1}) is None


def test_invalid_payload_returns_none():
    assert PskReporterConnector._to_spot(b"not json") is None
    assert PskReporterConnector._to_spot(b"[1, 2, 3]") is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("FT8", Mode.FT8),
        ("ft4", Mode.FT4),
        ("CW", Mode.CW),
        ("RTTY", Mode.RTTY),
        ("PSK31", Mode.PSK),
        ("PSK63", Mode.PSK),
        ("USB", Mode.SSB),
        ("JS8", Mode.UNKNOWN),
        (None, Mode.UNKNOWN),
        (7, Mode.UNKNOWN),
    ],
)
def test_adif_mode_mapping(value, expected):
    assert adif_mode(value) is expected


def test_config_defaults_to_disabled():
    cfg = PskReporterConfig()
    assert cfg.enabled is False
    assert cfg.host == "mqtt.pskreporter.info"
    assert cfg.port == 1883
    assert cfg.topic == "pskr/filter/v2/#"