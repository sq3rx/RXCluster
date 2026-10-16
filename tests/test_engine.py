import asyncio
from datetime import UTC, datetime

from rxcluster.config import VoacapConfig
from rxcluster.enrich.voacap.engine import VoacapEngine
from rxcluster.models import PathClass

FAKE_OUTPUT = """
     CCIR Coefficients        METHOD 30   VOACAP 16.1207W  PAGE   1

  Jun    1994          SSN = 100.
   5.0 15.0  1.8  3.7  7.1 10.1 14.1 18.1 21.1 24.9 28.1  0.0  0.0 FREQ
        1F2  2F2  2F2  1F2  1F2  1F2  1F2  1F2  1F2  1F2   -    -  MODE
       0.10 0.90 0.95 1.00 0.99 0.85 0.60 0.30 0.05 0.01   -    -  REL
"""


class FakeRunner:
    available = True
    engine = "fake-voacapl"
    itshfbc = "/fake/itshfbc"

    def __init__(self) -> None:
        self.calls = 0

    def run(self, deck: str, tag: str) -> str:
        self.calls += 1
        return FAKE_OUTPUT


def test_precompute_matrix_and_predict():
    cfg = VoacapConfig(target_grid_degrees=90, precompute=True)
    engine = VoacapEngine(cfg, "JO90AA")
    runner = FakeRunner()
    engine.runner = runner

    run_cells = asyncio.run(engine.precompute())
    assert run_cells > 0
    assert runner.calls == run_cells
    assert engine.matrix_size > 0

    when = datetime(2026, 6, 1, 5, tzinfo=UTC)
    # 20m representative frequency 14.10 MHz maps to the 13.7 column (REL 1.00).
    assert engine.predict("JO90AA", "20m", 14100.0, "CW", when=when) is PathClass.HIGH
    # 10m representative frequency 28.10 MHz: closest column is 25.9 (REL 0.09).
    assert engine.predict("JO90AA", "10m", 28100.0, "CW", when=when) is PathClass.UNLIKELY


def test_predict_without_precompute_uses_fallback():
    cfg = VoacapConfig(target_grid_degrees=90)
    engine = VoacapEngine(cfg, "JO90AA")
    # No precompute has run, so the empirical fallback must answer.
    result = engine.predict("JO90AA", "20m", 14100.0, "CW")
    assert isinstance(result, PathClass)