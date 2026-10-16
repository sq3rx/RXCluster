from rxcluster.enrich.voacap.voacapl import (
    BAND_FREQ_INDEX,
    FREQS_MHZ,
    build_deck,
    nearest_rel,
    parse_rel,
    rel_to_path,
)
from rxcluster.models import PathClass

SAMPLE_OUTPUT = """
     CCIR Coefficients        METHOD 30   VOACAP 16.1207W  PAGE   1

  Jun    1994          SSN = 100.
   5.0 17.3  6.1  7.2  9.7 11.9 13.7 15.4 17.7 21.6 25.9  0.0  0.0 FREQ
        1F2  2F2  2F2  1F2  1F2  1F2  1F2  1F2  1F2  1F2   -    -  MODE
        0.97 0.96 0.97 1.00 1.00 1.00 0.99 0.94 0.73 0.09   -    -  REL

     CCIR Coefficients        METHOD 30   VOACAP 16.1207W  PAGE   2
   6.0 19.1  6.1  7.2  9.7 11.9 13.7 15.4 17.7 21.6 25.9  0.0  0.0 FREQ
        0.97 0.79 0.91 1.00 1.00 1.00 1.00 0.98 0.89 0.49   -    -  REL
"""


def test_build_deck_cards():
    deck = build_deck(50.0, 10.0, -30.0, 120.0, 2026, 6, 100)
    lines = deck.splitlines()
    labels = [line[:10].strip() for line in lines]
    assert "COEFFS" in labels
    assert "TIME" in labels
    assert "MONTH" in labels
    assert "SUNSPOT" in labels
    assert "CIRCUIT" in labels
    assert "SYSTEM" in labels
    assert "ANTENNA" in labels
    assert "FREQUENCY" in labels
    assert labels[-2:] == ["EXECUTE", "QUIT"]
    freq_line = next(line for line in lines if line.startswith("FREQUENCY"))
    # 11 fields of width 5 after the 10-char label.
    assert len(freq_line[10:]) == 55


def test_deck_circuit_hemispheres():
    deck = build_deck(50.0, -10.0, -30.0, 120.0, 2026, 6, 100)
    circuit = next(line for line in deck.splitlines() if line.startswith("CIRCUIT"))
    assert "50.00N" in circuit
    assert "10.00W" in circuit
    assert "30.00S" in circuit
    assert "120.00E" in circuit


def test_parse_rel():
    parsed = parse_rel(SAMPLE_OUTPUT)
    assert 5 in parsed and 6 in parsed
    assert len(parsed[5]) == 9  # 11 frequencies minus the two zero columns
    rows = parsed[5]
    # The MUF column (17.3) is excluded.
    assert all(abs(freq - 17.3) > 0.01 for freq, _ in rows)
    assert nearest_rel(rows, 6.1) == 0.96
    assert nearest_rel(rows, 13.7) == 1.00
    # 25.9 is the last real frequency.
    assert nearest_rel(rows, 25.9) == 0.09


def test_nearest_rel_tolerance():
    rows = [(1.85, 0.9), (14.10, 0.2)]
    assert nearest_rel(rows, 14.10) == 0.2
    assert nearest_rel(rows, 20.0) is None  # outside tolerance


def test_rel_to_path_thresholds():
    assert rel_to_path(None) is PathClass.INSUFFICIENT
    assert rel_to_path(0.0) is PathClass.CLOSED
    assert rel_to_path(0.05) is PathClass.UNLIKELY
    assert rel_to_path(0.3) is PathClass.LOW
    assert rel_to_path(0.5) is PathClass.MEDIUM
    assert rel_to_path(0.9) is PathClass.HIGH


def test_frequency_table_shape():
    assert len(FREQS_MHZ) == 11
    assert set(BAND_FREQ_INDEX) == {"160m", "80m", "40m", "30m", "20m", "17m", "15m", "12m", "10m"}
    for index in BAND_FREQ_INDEX.values():
        assert 0 <= index < len(FREQS_MHZ)