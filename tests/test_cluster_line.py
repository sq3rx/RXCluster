from rxcluster.models import Mode, Source, SourceType
from rxcluster.parse.cluster_line import mode_from_text, parse_cluster_line


def test_parse_rbn_line():
    line = "DX de W3LPL-#:     7003.0  K1ABC            CW    12 dB  28 WPM  CQ      1234Z"
    spot = parse_cluster_line(line, Source.RBN, SourceType.SKIMMER)
    assert spot is not None
    assert spot.spotter == "W3LPL"
    assert spot.dx_call == "K1ABC"
    assert spot.freq_khz == 7003.0
    assert spot.mode is Mode.CW
    assert spot.snr == 12
    assert spot.speed_wpm == 28
    assert spot.source is Source.RBN
    assert spot.source_type is SourceType.SKIMMER


def test_parse_human_line():
    line = "DX de DL1ABC:    14025.0  VP2E            599 nice signal         1830Z"
    spot = parse_cluster_line(line, Source.VE7CC, SourceType.HUMAN)
    assert spot is not None
    assert spot.dx_call == "VP2E"
    assert spot.mode is Mode.UNKNOWN
    assert "nice signal" in spot.comment


def test_parse_rejects_non_dx_line():
    assert parse_cluster_line("Welcome to the cluster", Source.RBN) is None


def test_mode_detection():
    assert mode_from_text("FT8 -12 dB") is Mode.FT8
    assert mode_from_text("RTTY 45 baud") is Mode.RTTY
    assert mode_from_text("ssb qso") is Mode.SSB
    assert mode_from_text("no mode here") is None