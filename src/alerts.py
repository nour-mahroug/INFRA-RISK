"""GeoJSON alert layer serialization."""
from __future__ import annotations
import json, logging
from pathlib import Path
from datetime import date
import geopandas as gpd

LOG = logging.getLogger(__name__)
PROPERTIES = ["asset_id", "name", "type", "velocity_mm_yr", "risk_score", "rank",
              "obs_start", "obs_end", "source"]

def build_alerts(frame: gpd.GeoDataFrame, cfg: dict, output_path: str | Path | None = None,
                 source: str | None = None) -> dict:
    """Write a valid GeoJSON FeatureCollection with the SmartSDG schema."""
    path = Path(output_path or cfg["paths"]["alerts"])
    path.parent.mkdir(parents=True, exist_ok=True)
    mode_source = source or ("SYNTHETIC_DEMO" if cfg.get("project", {}).get("mode") == "demo"
                             else "Sentinel-1 / HyP3 / MintPy")
    features = []
    for _, row in frame.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        props = {
            "asset_id": str(row["asset_id"]), "name": str(row["name"]),
            "type": str(row["type"]), "velocity_mm_yr": float(row.get("velocity_mean", 0.0)),
            "risk_score": float(row.get("risk_score", 0.0)), "rank": int(row.get("rank", 0)),
            "obs_start": str(cfg["dates"]["start"]), "obs_end": str(cfg["dates"]["end"]),
            "source": mode_source,
        }
        features.append({"type": "Feature", "geometry": geom.__geo_interface__, "properties": props})
    collection = {"type": "FeatureCollection", "features": features,
                  "metadata": {"project": "INFRA-RISK Tunisia",
                               "positioning": "Screening and prioritization, not failure prediction",
                               "source": mode_source, "feature_count": len(features)}}
    with path.open("w", encoding="utf-8") as stream:
        json.dump(collection, stream, ensure_ascii=False, indent=2, allow_nan=False)
    LOG.info("Wrote %d GeoJSON features to %s", len(features), path)
    return collection

def read_alerts(path: str | Path) -> dict:
    """Load an existing GeoJSON FeatureCollection."""
    with Path(path).open("r", encoding="utf-8") as stream:
        data = json.load(stream)
    if data.get("type") != "FeatureCollection":
        raise ValueError("Expected a GeoJSON FeatureCollection")
    return data
