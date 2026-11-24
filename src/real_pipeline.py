from __future__ import annotations
import argparse, copy, logging
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


class ScreeningError(Exception):
    """Expected failure (bad input, no coverage, OSM down). The API maps it to HTTP `status`."""

    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def raster_window(raster_path: str | Path) -> dict:
    """Cheap read of the raster tags (observation window, pairs, reference) without loading pixels."""
    import rasterio
    with rasterio.open(raster_path) as src:
        return dict(src.tags())


def _clean_names(assets):
    """OpenStreetMap leaves many assets unnamed: label them 'Unnamed <type>' instead of 'nan'."""
    assets = assets.copy()
    bad = assets["name"].isna() | assets["name"].astype(str).str.strip().str.lower().isin(["", "nan", "none"])
    assets.loc[bad, "name"] = "Unnamed " + assets.loc[bad, "type"].astype(str).str.replace("_", " ")
    return assets


def _load_assets(cfg: dict):
    """Real OpenStreetMap assets; an Overpass outage becomes a 503, not a crash."""
    try:
        return _clean_names(extract_osm_assets(cfg, demo=False))
    except Exception as exc:
        raise ScreeningError(f"OpenStreetMap (Overpass) unavailable: {exc}", status=503) from exc


def load_real_points(raster_path: str | Path) -> tuple[gpd.GeoDataFrame, dict]:
    """Turn the 3-band velocity GeoTIFF into points carrying velocity and real coherence."""
    import rasterio
    from rasterio.transform import xy
    from shapely.geometry import Point
    with rasterio.open(raster_path) as src:
        tags = src.tags()
        if not str(tags.get("SOURCE", "")).startswith("Sentinel-1"):
            raise ScreeningError(
                f"{raster_path} is not tagged as Sentinel-1 data; refusing to label it as real.", status=503)
        velocity = src.read(1, masked=True)
        velocity = velocity - np.ma.median(velocity)                     # assume most of the area is stable
        velocity = np.ma.masked_where(np.abs(velocity) > 50, velocity)   # drop likely unwrapping errors
        coherence = src.read(2, masked=True)
        rows, cols = np.nonzero(~np.ma.getmaskarray(velocity))
        xs, ys = xy(src.transform, rows, cols, offset="center")
    frame = gpd.GeoDataFrame(
        {"velocity_mm_yr": np.asarray(velocity[rows, cols], dtype=float),
         "coherence": np.asarray(coherence[rows, cols], dtype=float)},
        geometry=[Point(x, y) for x, y in zip(xs, ys)], crs="EPSG:4326")
    return frame, tags


def _score_area(cfg: dict, points: gpd.GeoDataFrame, tags: dict):
    """Shared by run_real and screen_area: associate, rank, and count what was not assessed."""
    cfg.setdefault("project", {})["mode"] = "production"
    cfg["dates"] = {"start": tags.get("OBS_START", cfg["dates"]["start"]),
                    "end": tags.get("OBS_END", cfg["dates"]["end"])}
    LOG.info("Real velocity points: %d (window %s to %s, %s pairs, reference: %s)", len(points),
             cfg["dates"]["start"], cfg["dates"]["end"], tags.get("N_PAIRS"), tags.get("REFERENCE"))
    assets = _load_assets(cfg)
    min_samples = int(cfg["assets"].get("min_samples", 3))
    # Pixels are ~80 m apart, so use a buffer large enough to reach the nearest valid pixel.
    associated = associate_assets(assets, points, max(int(cfg["assets"]["buffer_m"]), 60))
    measured = associated[associated["sample_count"] >= min_samples].copy()
    if measured.empty:
        raise ScreeningError(f"No asset in this area has a reliable measurement (>= {min_samples} radar pixels).")
    radius = float(cfg["anomaly"].get("neighbourhood_m", 1500))
    # anomalies are computed on velocity relative to the neighbourhood
    scored = score_assets(to_relative(measured, points, radius), cfg)
    scored["velocity_rel_mm_yr"] = scored["velocity_mean"]   # neighbourhood-relative value
    scored["velocity_mean"] = scored["velocity_abs"]         # reports keep the real LOS velocity
    n_found, n_ranked = len(associated), len(measured)
    LOG.info("%d of %d assets have >= %d reliable pixels and are ranked; the rest are reported as "
             "insufficient data.", n_ranked, n_found, min_samples)
    meta = {"assets_found": n_found, "assets_ranked": n_ranked,
            "assets_insufficient_data": n_found - n_ranked, "min_samples": min_samples,
            "coverage_note": f"{n_ranked} of {n_found} assets ranked; the rest had insufficient radar data "
                             f"(not 'safe').",
            "obs_start": cfg["dates"]["start"], "obs_end": cfg["dates"]["end"],
            "n_pairs": tags.get("N_PAIRS"), "reference": tags.get("REFERENCE")}
    return scored, meta


def run_real(config_path: str, raster: str, out_dir: str) -> gpd.GeoDataFrame:
    """Full run on the real raster: writes alerts.geojson, map.html and ranked_assets.csv."""
    cfg = load_config(config_path)
    ensure_directories(cfg)
    points, tags = load_real_points(raster)
    scored, meta = _score_area(cfg, points, tags)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    build_alerts(scored, cfg, output_path=out / "alerts.geojson", source=SOURCE_TAG, extra_metadata=meta)
    create_map(scored, cfg, output_path=out / "map.html", meta=meta)
    scored.drop(columns="geometry").to_csv(out / "ranked_assets.csv", index=False)
    LOG.info("Real-data outputs written to %s", out)
    return scored


def screen_area(cfg: dict, bbox: list[float], raster: str) -> dict:
    """Live screening of a bbox covered by the real raster (in memory, used by the API)."""
    cfg = copy.deepcopy(cfg)
    cfg["aoi"]["bbox"] = [float(v) for v in bbox]
    points, tags = load_real_points(raster)
    west, south, east, north = cfg["aoi"]["bbox"]
    points = points.cx[west:east, south:north]
    if points.empty:
        raise ScreeningError("The requested area is outside the radar coverage (no reliable Sentinel-1 pixel).")
    scored, meta = _score_area(cfg, points, tags)
    return build_alerts(scored, cfg, output_path=None, source=SOURCE_TAG, extra_metadata=meta, write=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="INFRA-RISK pipeline on real Sentinel-1 data")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--raster", default="data/processed/velocity_real.tif")
    parser.add_argument("--out", default="outputs/real")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        run_real(args.config, args.raster, args.out)
    except ScreeningError as exc:
        raise SystemExit(f"ERROR: {exc}")


if __name__ == "__main__":
    main()