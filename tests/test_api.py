import pytest
from fastapi.testclient import TestClient
from src import api
from src.real_pipeline import ScreeningError

BODY = {"area": [10.10, 36.74, 10.34, 36.86], "start_date": "2024-07-09", "end_date": "2025-06-04"}
FAKE = {"type": "FeatureCollection", "features": [],
        "metadata": {"feature_count": 0, "obs_start": "2024-07-09", "obs_end": "2025-06-04"}}


@pytest.fixture
def client(tmp_path, monkeypatch):
    raster = tmp_path / "v.tif"
    raster.write_bytes(b"x")
    monkeypatch.setattr(api, "RASTER", raster)
    monkeypatch.setattr(api, "raster_window", lambda _p: {"OBS_START": "2024-07-09", "OBS_END": "2025-06-04"})
    monkeypatch.setattr(api, "screen_area", lambda cfg, bbox, r: FAKE)
    api._cached.cache_clear()
    return TestClient(api.app)


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_good_bbox(client):
    r = client.post("/screen", json=BODY)
    assert r.status_code == 200 and r.json()["type"] == "FeatureCollection"


@pytest.mark.parametrize("area", [
    [10.34, 36.74, 10.10, 36.86],      # west > east
    [10.10, 36.86, 10.34, 36.74],      # south > north
    [2.2, 48.8, 2.5, 48.9],            # Paris, outside Tunisia
    [8.0, 31.0, 11.0, 37.0],           # too large
    [10.1, 36.7],                      # wrong length
])
def test_bad_bbox_is_422(client, area):
    assert client.post("/screen", json={**BODY, "area": area}).status_code == 422


def test_dates_reversed(client):
    assert client.post("/screen", json={**BODY, "start_date": "2025-06-04", "end_date": "2024-07-09"}).status_code == 422


def test_period_outside_window(client):
    r = client.post("/screen", json={**BODY, "start_date": "2020-01-01", "end_date": "2020-12-31"})
    assert r.status_code == 422 and "overlap" in r.json()["detail"]


def test_no_coverage_is_422(client, monkeypatch):
    def boom(cfg, bbox, r):
        raise ScreeningError("outside the radar coverage")
    monkeypatch.setattr(api, "screen_area", boom)
    api._cached.cache_clear()
    assert client.post("/screen", json=BODY).status_code == 422


def test_overpass_down_is_503(client, monkeypatch):
    def boom(cfg, bbox, r):
        raise ScreeningError("Overpass unavailable", status=503)
    monkeypatch.setattr(api, "screen_area", boom)
    api._cached.cache_clear()
    assert client.post("/screen", json=BODY).status_code == 503


def test_missing_raster_is_503(client, monkeypatch, tmp_path):
    monkeypatch.setattr(api, "RASTER", tmp_path / "nope.tif")
    assert client.post("/screen", json=BODY).status_code == 503