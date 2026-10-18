from rxcluster.config import Config, NearbyConfig


def test_nearby_defaults():
    cfg = NearbyConfig()
    assert cfg.radius_km == 700.0
    assert cfg.low_band_radius_km == 1500.0
    assert cfg.low_bands == ["160m", "80m", "60m"]


def test_nearby_from_config():
    cfg = Config.model_validate(
        {"pipeline": {"nearby": {"radius_km": 500, "low_bands": ["160m", "80m"]}}}
    )
    assert cfg.pipeline.nearby.radius_km == 500.0
    assert cfg.pipeline.nearby.low_band_radius_km == 1500.0
    assert cfg.pipeline.nearby.low_bands == ["160m", "80m"]


def test_removed_toxic_switch_is_ignored():
    # Pre-0.3.0 configs carry switches.toxic; it must load and be ignored.
    cfg = Config.model_validate({"defaults": {"switches": {"beacon": True, "toxic": False}}})
    assert cfg.defaults.switches.beacon is True
    assert not hasattr(cfg.defaults.switches, "toxic")
