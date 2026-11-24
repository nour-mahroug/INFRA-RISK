from __future__ import annotations
import argparse, logging
from pathlib import Path
import geopandas as gpd
import numpy as np

from .config import load_config, ensure_directories
from .assets import extract_osm_assets, associate_assets
from .anomalies import score_assets
from .alerts import build_alerts
from .map import create_map
from .stacking import SOURCE_TAG
from .neighbourhood import to_relative

LOG = logging.getLogger(__name__)


def _clean_names(assets):
    """OpenStreetMap leaves many assets unnamed: label them 'Unnamed <type>' instead of 'nan'."""
    assets = assets.copy()
    bad = assets["name"].isna() | assets["name"].astype(str).str.strip().str.lower().isin(["", "nan", "none"])
    assets.loc[bad, "name"] = "Unnamed " + assets.loc[bad, "type"].astype(str).str.replace("_", " ")
    return assets


def load_real_points(raster_path: str | Path) -> tuple[gpd.GeoDataFrame, dict]:
    """Turn the 3-band velocity GeoTIFF into points carrying velocity and real coherence."""
    import rasterio
    from rasterio.transform import xy
    from shapely.geometry import Point
    with rasterio.open(raster_path) as src:
        tags = src.tags()
        if not str(tags.get("SOURCE", "")).startswith("Sentinel-1"):
            raise SystemExit(f"{raster_path} is not tagged as Sentinel-1 data; refusing to label it as real.")
        velocity = src.read(1, masked=True)
        velocity = velocity - np.ma.median(velocity)   # assume most of the area is stable
        velocity = np.ma.masked_where(np.abs(velocity) > 50, velocity)   # drop likely unwrapping errors
        coherence = src.read(2, masked=True)
        rows, cols = np.nonzero(~np.ma.getmaskarray(velocity))
        xs, ys = xy(src.transform, rows, cols, offset="center")
    frame = gpd.GeoDataFrame(
        {"velocity_mm_yr": np.asarray(velocity[rows, cols], dtype=float),
         "coherence": np.asarray(coherence[rows, cols], dtype=float)},
        geometry=[Point(x, y) for x, y in zip(xs, ys)], crs="EPSG:4326")
    return frame, tags


def run_real(config_path: str, raster: str, out_dir: str) -> gpd.GeoDataFrame:
    cfg = load_config(config_path)
    ensure_directories(cfg)
    points, tags = load_real_points(raster)
    cfg.setdefault("project", {})["mode"] = "production"
    cfg["dates"] = {"start": tags.get("OBS_START", cfg["dates"]["start"]),
                    "end": tags.get("OBS_END", cfg["dates"]["end"])}
    LOG.info("Real velocity points: %d (window %s to %s, %s pairs, reference: %s)", len(points),
             cfg["dates"]["start"], cfg["dates"]["end"], tags.get("N_PAIRS"), tags.get("REFERENCE"))
    assets = _clean_names(extract_osm_assets(cfg, demo=False))  # real OpenStreetMap assets, raises on failure
    # Pixels are ~80 m apart, so use a buffer large enough to reach the nearest valid pixel.
    buffer_m = max(int(cfg["assets"]["buffer_m"]), 60)
    associated = associate_assets(assets, points, buffer_m)
    measured = associated[associated["sample_count"] >= int(cfg["assets"].get("min_samples", 3))].copy()
    LOG.info("%d of %d assets have >= %d reliable pixels and are ranked; the rest are reported as insufficient data.",
             len(measured), len(associated), int(cfg["assets"].get("min_samples", 3)))
    if measured.empty:
        raise SystemExit("No asset has a reliable measurement. Check the velocity map and coherence threshold.")
    radius = float(cfg["anomaly"].get("neighbourhood_m", 1500))
    scored = score_assets(to_relative(measured, points, radius), cfg)  # anomalies on velocity relative to neighbourhood
    scored["velocity_mean"] = scored["velocity_abs"]                    # reports keep the real LOS velocity
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    build_alerts(scored, cfg, output_path=out / "alerts.geojson", source=SOURCE_TAG)
    create_map(scored, cfg, output_path=out / "map.html")
    scored.drop(columns="geometry").to_csv(out / "ranked_assets.csv", index=False)
    LOG.info("Real-data outputs written to %s", out)
    return scored


def main() -> None:
    parser = argparse.ArgumentParser(description="INFRA-RISK pipeline on real Sentinel-1 data")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--raster", default="data/processed/velocity_real.tif")
    parser.add_argument("--out", default="outputs/real")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run_real(args.config, args.raster, args.out)




def screen_area(cfg: dict, bbox: list[float], raster: str) -> dict:
    """Live screening of any bbox covered by the real raster: OSM + scoring + GeoJSON (in memory)."""
    import copy, tempfile, json
    cfg = copy.deepcopy(cfg)
    cfg["aoi"]["bbox"] = [float(v) for v in bbox]
    points, tags = load_real_points(raster)
    west, south, east, north = cfg["aoi"]["bbox"]
    points = points.cx[west:east, south:north]
    if points.empty:
        raise SystemExit("The requested area has no reliable Sentinel-1 pixel.")
    cfg.setdefault("project", {})["mode"] = "production"
    cfg["dates"] = {"start": tags.get("OBS_START", cfg["dates"]["start"]),
                    "end": tags.get("OBS_END", cfg["dates"]["end"])}
    assets = _clean_names(extract_osm_assets(cfg, demo=False))
    associated = associate_assets(assets, points, max(int(cfg["assets"]["buffer_m"]), 60))
    measured = associated[associated["sample_count"] >= int(cfg["assets"].get("min_samples", 3))].copy()
    if measured.empty:
        raise SystemExit("No asset in this area has a reliable measurement.")
    radius = float(cfg["anomaly"].get("neighbourhood_m", 1500))
    scored = score_assets(to_relative(measured, points, radius), cfg)
    scored["velocity_mean"] = scored["velocity_abs"]
    with tempfile.TemporaryDirectory() as tmp:
        build_alerts(scored, cfg, output_path=Path(tmp) / "a.geojson", source=SOURCE_TAG)
        data = json.loads((Path(tmp) / "a.geojson").read_text(encoding="utf-8"))
    data["metadata"].update({"obs_start": cfg["dates"]["start"], "obs_end": cfg["dates"]["end"],
                             "n_pairs": tags.get("N_PAIRS"), "reference": tags.get("REFERENCE")})
    return data


if __name__ == "__main__":
    main()