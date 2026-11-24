"""Tests for GeoJSON schema and serialization."""
import json
import geopandas as gpd
from shapely.geometry import Point
from src.alerts import build_alerts

def test_geojson_schema(tmp_path):
    cfg = {"dates":{"start":"2022-01-01","end":"2025-06-30"},
           "paths":{"alerts":str(tmp_path/"alerts.geojson")},
           "project":{"mode":"demo"}}
    frame = gpd.GeoDataFrame([{
        "asset_id":"abc123","name":"Demo bridge","type":"bridge",
        "velocity_mean":2.3,"risk_score":71.2,"rank":1,
        "geometry":Point(10.2,36.8)
    }], crs="EPSG:4326")
    result = build_alerts(frame,cfg)
    saved = json.loads((tmp_path/"alerts.geojson").read_text())
    assert result["type"] == "FeatureCollection"
    props = saved["features"][0]["properties"]
    assert set(["asset_id","name","type","velocity_mm_yr","risk_score","rank",
                "obs_start","obs_end","source"]).issubset(props)
    assert props["source"] == "SYNTHETIC_DEMO"
