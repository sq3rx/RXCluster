from rxcluster.config import DxSummitConfig
from rxcluster.models import Source, SourceType
from rxcluster.sources.dxsummit import DxSummitConnector


def _parse(record: dict):
    connector = DxSummitConnector(DxSummitConfig(), lambda spot: None)
    return connector._to_spot(record)


def test_de_call_is_used_as_spotter():
    record = {
        "info": "up1",
        "dx_country": "Montserrat",
        "de_latitude": 28.32,
        "dx_latitude": 16.75,
        "dx_longitude": 62.18,
        "de_call": "EA8TL",
        "frequency": 24895.1,
        "time": "2026-10-16T18:58:28",
        "dx_call": "VP2MAW",
        "de_longitude": 15.85,
        "id": 68552892,
    }
    spot = _parse(record)
    assert spot is not None
    assert spot.spotter == "EA8TL"
    assert spot.dx_call == "VP2MAW"
    assert spot.source is Source.DXSUMMIT
    assert spot.source_type is SourceType.HUMAN
    assert spot.comment == "up1"
    assert spot.freq_khz == 24895.1
    # DX Summit longitudes are west-positive, so the grids must be flipped.
    assert spot.dx_grid == "FK86"
    assert spot.spotter_grid == "IL28"


def test_missing_de_call_falls_back_to_dxsummit():
    record = {
        "dx_call": "K1ABC",
        "frequency": 14025.0,
        "time": "2026-10-16T18:58:28",
        "id": 1,
    }
    spot = _parse(record)
    assert spot is not None
    assert spot.spotter == "DXSUMMIT"
    assert spot.dx_grid == ""
    assert spot.spotter_grid == ""


def test_east_hemisphere_longitude_sign():
    record = {
        "de_call": "JA1JXT",
        "dx_call": "6Y5XX",
        "dx_latitude": 18.0,
        "dx_longitude": 77.0,
        "de_latitude": 35.6,
        "de_longitude": -139.68,
        "frequency": 21025.0,
        "time": "2026-10-16T18:58:28",
        "id": 2,
    }
    spot = _parse(record)
    assert spot is not None
    # Japan (~139E) is stored as -139.68 (west-positive) and must map to the
    # PM field, not the opposite side of the globe.
    assert spot.spotter_grid.startswith("PM")
