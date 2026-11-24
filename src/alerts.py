from __future__ import annotations
import json, logging, math
from pathlib import Path
import geopandas as gpd

LOG = logging.getLogger(__name__)
PROPERTIES = ["asset_id", "name", "type", "velocity_mm_yr", "risk_score", "rank",
              "obs_start", "obs_end", "source"]
OPTIONAL_PROPERTIES = ["priority", "sample_count", "velocity_rel_mm_yr"]


def _num(value, ndigits: int = 2):
    """float rounded, or None for missing/NaN (JSON has no NaN)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) or math.isinf(v) else round(v, ndigits)


def build_alerts(frame: gpd.GeoDataFrame, cfg: dict, output_path: str | Path | None = None,
                 source: str | None = None, extra_metadata: dict | None = None,
                 write: bool = True) -> dict:
    """Build (and optionally write) a GeoJSON FeatureCollection with the SmartSDG schema."""
    mode_source = source or ("SYNTHETIC_DEMO" if cfg.get("project", {}).get("mode") == "demo"
                             else "Sentinel-1 / HyP3 / stacking")
    features = []
    for _, row in frame.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        sc = row.get("sample_count")
        pr = row.get("priority")
        props = {
            "asset_id": str(row["asset_id"]), "name": str(row["name"]), "type": str(row["type"]),
            "velocity_mm_yr": _num(row.get("velocity_mean")),
            "risk_score": _num(row.get("risk_score", 0.0), 1) or 0.0,
            "rank": int(row.get("rank", 0)),
            "obs_start": str(cfg["dates"]["start"]), "obs_end": str(cfg["dates"]["end"]),
            "source": mode_source,
            "priority": None if pr is None or str(pr) == "nan" else str(pr),
            "sample_count": None if sc is None or _num(sc) is None else int(sc),
            "velocity_rel_mm_yr": _num(row.get("velocity_rel_mm_yr")),
        }
        features.append({"type": "Feature", "geometry": geom.__geo_interface__, "properties": props})
    metadata = {"project": "INFRA-RISK Tunisia",
                "positioning": "Screening and prioritization, not failure prediction",
                "source": mode_source, "feature_count": len(features),
                "rank_definition": "Tiered: high priority first, then medium, then low; risk score within each tier.",
                "velocity_convention": "Line-of-sight, mm/yr, positive = toward the satellite"}
    metadata.update(extra_metadata or {})
    collection = {"type": "FeatureCollection", "features": features, "metadata": metadata}
    if write:
        path = Path(output_path or cfg["paths"]["alerts"])
        path.parent.mkdir(parents=True, exist_ok=True)
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