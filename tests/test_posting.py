import pytest

from rxcluster.bus.pubsub import SpotBus, Subscriber
from rxcluster.config import Config
from rxcluster.enrich.enricher import Enricher
from rxcluster.filters.compiled import compile_filter
from rxcluster.filters.model import FilterState
from rxcluster.filters.parser import CommandHandlers, PostRequest, parse_command
from rxcluster.models import Source, SourceType, Spot
from rxcluster.parse.freq import BandPlan
from rxcluster.pipeline import Pipeline
from rxcluster.validate.cty import CtyDatabase
from rxcluster.validate.scp import ScpDatabase
from rxcluster.validate.validator import Validator


def build_pipeline() -> tuple[Pipeline, SpotBus]:
    cfg = Config()
    cfg.pipeline.enrichment.voacap.enabled = False
    band_plan = BandPlan(cfg.band_ranges, cfg.mode_subbands)
    validator = Validator(cfg.pipeline.validation, ScpDatabase(), CtyDatabase())
    enricher = Enricher(cfg.pipeline.enrichment, cfg.station.operator_grid)
    bus = SpotBus()
    pipeline = Pipeline(cfg.pipeline, band_plan, validator, enricher, bus)
    return pipeline, bus


def test_dx_command_parses_and_posts():
    state = FilterState()
    captured: dict[str, PostRequest] = {}

    def post(request: PostRequest) -> str:
        captured["req"] = request
        return "Spot accepted."

    result = parse_command(
        "DX 14025.0 K1ABC CQ test",
        state,
        CommandHandlers(post_handler=post),
    )
    assert result.post is not None
    assert result.post.dx_call == "K1ABC"
    assert result.post.freq_khz == 14025.0
    assert captured["req"].comment == "CQ test"
    assert result.responses == ["Spot accepted."]


def test_dx_rejects_bad_frequency_and_comment():
    state = FilterState()
    assert "frequency" in parse_command("DX abc K1ABC", state).responses[0]
    assert "out of range" in parse_command("DX 999999 K1ABC", state).responses[0]
    assert "unsupported" in parse_command("DX 14025 K1ABC bad;comment", state).responses[0]


def test_post_manual_delivers_to_subscriber():
    pipeline, bus = build_pipeline()
    sub = Subscriber("N0CALL", compile_filter(FilterState(), "N0CALL"))
    bus.subscribe(sub)
    response = pipeline.post_manual("N0CALL", PostRequest(14025.0, "K1ABC", "CQ"))
    assert response == "Spot accepted."
    assert not sub.queue.empty()
    line = sub.queue.get_nowait()
    assert "K1ABC" in line


def test_dx_command_end_to_end():
    pipeline, bus = build_pipeline()
    sub = Subscriber("N0CALL", compile_filter(FilterState(), "N0CALL"))
    bus.subscribe(sub)
    result = parse_command(
        "DX 14025.0 K1ABC CQ",
        FilterState(),
        CommandHandlers(
            operator_call="N0CALL",
            post_handler=lambda req: pipeline.post_manual("N0CALL", req),
        ),
    )
    assert result.responses == ["Spot accepted."]


@pytest.mark.parametrize("policy", ["FAST", "MED", "SLOW"])
def test_set_dedupe_policy(policy):
    state = FilterState()
    stored: dict[str, str] = {}

    def setter(value: str) -> None:
        stored["policy"] = value

    result = parse_command(
        f"SET DEDUPE {policy}",
        state,
        CommandHandlers(dedupe_setter=setter, dedupe_provider=lambda: stored.get("policy", "")),
    )
    assert stored["policy"] == policy
    assert policy in result.responses[0]


def test_set_dedupe_rejects_unknown():
    result = parse_command("SET DEDUPE TURBO", FilterState())
    assert "FAST" in result.responses[0]


def test_who_spots_me():
    pipeline, bus = build_pipeline()
    sub = Subscriber("N0CALL", compile_filter(FilterState(), "N0CALL"))
    bus.subscribe(sub)
    spot = Spot(
        source=Source.RBN,
        source_type=SourceType.SKIMMER,
        spotter="DL1ABC",
        dx_call="N0CALL",
        freq_khz=14025.0,
        timestamp=0.0,
        spotter_dxcc="Germany",
        spotter_continent="EU",
    )
    pipeline.process(spot)
    lines = pipeline.who_spots_me("20m", "N0CALL")
    assert lines[0].startswith("WHOSPOTSME 20M")
    assert any("Germany" in line for line in lines[1:])


def test_prop_outlook_empirical_fallback():
    cfg = Config()
    cfg.station.operator_grid = "FN31"
    cfg.pipeline.enrichment.voacap.enabled = True
    band_plan = BandPlan(cfg.band_ranges, cfg.mode_subbands)
    validator = Validator(cfg.pipeline.validation, ScpDatabase(), CtyDatabase())
    enricher = Enricher(cfg.pipeline.enrichment, cfg.station.operator_grid)
    pipeline = Pipeline(cfg.pipeline, band_plan, validator, enricher, SpotBus())

    lines = pipeline.prop_outlook("FN42", "20m", "CW")
    assert lines[0].startswith("PROP FN31 -> FN42")
    assert len(lines) >= 2


def test_prop_outlook_without_grid():
    pipeline, _bus = build_pipeline()
    assert "disabled" in pipeline.prop_outlook("FN42", "20m", "CW")[0].lower()
