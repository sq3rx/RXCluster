from rxcluster.config import TagsConfig
from rxcluster.enrich.tags import n2wq_mode_token, render_line
from rxcluster.models import Confidence, Mode, PathClass, Source, SourceType, Spot

WIDTH = 76


def test_render_line_is_fixed_width_n2wq_format():
    spot = Spot(
        source=Source.RBN,
        source_type=SourceType.SKIMMER,
        spotter="W1ABC",
        dx_call="K1XYZ",
        freq_khz=14074.0,
        timestamp=0.0,
        comment="CQ",
        mode=Mode.CW,
        band="20m",
        snr=25,
        speed_wpm=28,
        dx_grid="FN31",
        confidence=Confidence.VALID,
        path=PathClass.HIGH,
    )
    line = render_line(spot, TagsConfig())
    assert line == "DX de W1ABC-#:   14074.00  K1XYZ       CW 25 dB 28 WPM CQ     > FN31 V 0000Z"
    assert len(line) == WIDTH


def test_render_line_columns_are_stable():
    spot = Spot(
        source=Source.RBN,
        source_type=SourceType.SKIMMER,
        spotter="W1ABC",
        dx_call="K1XYZ",
        freq_khz=14074.0,
        timestamp=0.0,
        comment="CQ",
        mode=Mode.FT8,
        band="20m",
        snr=-12,
        dx_grid="FN31",
        confidence=Confidence.VALID,
        path=PathClass.HIGH,
    )
    line = render_line(spot, TagsConfig())
    assert len(line) == WIDTH
    # mode starts at column 40 (1-based) -> index 39
    assert line[39:43] == "FT8 "
    # frequency ends at column 25
    assert line[17:25] == "14074.00"
    # path glyph at column 63 -> index 62
    assert line[62] == ">"
    # grid at columns 65-68 -> indices 64:68
    assert line[64:68] == "FN31"
    # confidence at column 70 -> index 69
    assert line[69] == "V"
    # time at columns 72-76 -> indices 71:76
    assert line[71:76] == "0000Z"


def test_render_line_human_without_snr():
    spot = Spot(
        source=Source.VE7CC,
        source_type=SourceType.HUMAN,
        spotter="DL1ABC",
        dx_call="VP2E",
        freq_khz=14025.0,
        timestamp=0.0,
        comment="nice signal",
        mode=Mode.SSB,
        band="20m",
        dx_grid="FN31",
        confidence=Confidence.LOW,
        path=PathClass.INSUFFICIENT,
    )
    line = render_line(spot, TagsConfig())
    assert "USB nice signal" in line
    assert line[39:42] == "USB"
    # Insufficient path renders as a blank glyph.
    assert line[62] == " "
    assert line[64:68] == "FN31"
    assert line[69] == "?"
    assert line[71:76] == "0000Z"
    assert len(line) == WIDTH


def test_render_line_report_sign():
    ft8 = Spot(
        source=Source.RBN,
        source_type=SourceType.SKIMMER,
        spotter="W1ABC",
        dx_call="K1XYZ",
        freq_khz=14074.0,
        timestamp=0.0,
        mode=Mode.FT8,
        band="20m",
        snr=12,
    )
    assert "+12 dB" in render_line(ft8, TagsConfig())

    cw = Spot(
        source=Source.RBN,
        source_type=SourceType.SKIMMER,
        spotter="W1ABC",
        dx_call="K1XYZ",
        freq_khz=7027.0,
        timestamp=0.0,
        mode=Mode.CW,
        band="40m",
        snr=12,
    )
    line = render_line(cw, TagsConfig())
    assert "CW 12 dB" in line
    assert "+12 dB" not in line


def test_n2wq_mode_token():
    assert n2wq_mode_token(Mode.CW, 7027.0) == "CW"
    assert n2wq_mode_token(Mode.RTTY, 7035.0) == "RTTY"
    assert n2wq_mode_token(Mode.PSK, 14070.0) == "PSK"
    assert n2wq_mode_token(Mode.FT8, 14074.0) == "FT8"
    assert n2wq_mode_token(Mode.FT4, 14080.0) == "FT4"
    assert n2wq_mode_token(Mode.SSB, 3600.0) == "LSB"
    assert n2wq_mode_token(Mode.SSB, 14200.0) == "USB"
    assert n2wq_mode_token(Mode.SSB, 5357.0, "60m") == "USB"
    assert n2wq_mode_token(Mode.UNKNOWN, 14000.0) is None


def test_render_line_rtty_uses_full_mode_name():
    spot = Spot(
        source=Source.RBN,
        source_type=SourceType.SKIMMER,
        spotter="W1ABC",
        dx_call="K1XYZ",
        freq_khz=7035.0,
        timestamp=0.0,
        comment="CQ",
        mode=Mode.RTTY,
        band="40m",
    )
    line = render_line(spot, TagsConfig())
    assert "RTTY CQ" in line
    assert line[39:43] == "RTTY"
    assert len(line) == WIDTH
