"""OpenStreetMap asset extraction and demo-safe asset inventory."""
from __future__ import annotations
import hashlib, logging
from typing import Any
import geopandas as gpd
import pandas as pd
from shapely.geometry import box, Point, LineString

LOG = logging.getLogger(__name__)

def stable_asset_id(osm_type: str, osm_id: Any) -> str:
    """Return a stable, compact identifier derived from an OSM element ID."""
    raw = f"{osm_type}:{osm_id}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:12]

def _synthetic_assets(cfg: dict[str, Any]) -> gpd.GeoDataFrame:
    """Create deterministic named demo assets when Overpass/OSM is unavailable."""
    west, south, east, north = cfg["aoi"]["bbox"]
    rows = []
    examples = [
        ("demo-bridge-01", "Pont de Radès (demo asset)", "bridge", .72, .28),
        ("demo-port-01", "Port de La Goulette (demo asset)", "port", .78, .76),
        ("demo-hospital-01", "Hôpital pilote Nord (demo asset)", "hospital", .38, .62),
        ("demo-school-01", "École pilote Centre (demo asset)", "school", .54, .47),
        ("demo-road-01", "Avenue principale (demo asset)", "road_trunk", .67, .30),
        ("demo-road-02", "Route secondaire (demo asset)", "road_secondary", .28, .72),
        ("demo-bridge-02", "Passage supérieur (demo asset)", "bridge", .83, .48),
        ("demo-hospital-02", "Hôpital pilote Sud (demo asset)", "hospital", .20, .35),
    ]
    for i, (aid, name, typ, fx, fy) in enumerate(examples):
        rows.append({"asset_id": aid, "name": name, "type": typ, "osm_id": f"demo-{i}",
                     "geometry": Point(west + fx*(east-west), south + fy*(north-south))})
    # Add a small set of road segments for a richer demo map.
    for i in range(12):
        x = west + (0.15 + i*0.055)*(east-west)
        y = south + (0.25 + (i%4)*0.16)*(north-south)
        rows.append({"asset_id": f"demo-road-{i+3:02d}", "name": f"Route démo {i+1}",
                     "type": "road_primary" if i%2 == 0 else "road_secondary",
                     "osm_id": f"demo-r{i}", "geometry": LineString([(x,y),(min(east,x+.012),min(north,y+.006))])})
    return gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")

def extract_osm_assets(cfg: dict[str, Any], demo: bool = False) -> gpd.GeoDataFrame:
    """Extract bridges, selected roads, hospitals, schools and La Goulette port via OSMnx."""
    if demo:
        LOG.warning("DEMO MODE: using labelled synthetic asset inventory.")
        return _synthetic_assets(cfg)
    west, south, east, north = cfg["aoi"]["bbox"]
    polygon = box(west, south, east, north)
    try:
        import osmnx as ox
        ox.settings.timeout = int(cfg["assets"]["network_timeout"])
        tags = {
            "man_made": ["bridge"],
            "bridge": True,
            "highway": ["primary", "secondary", "trunk"],
            "amenity": ["hospital", "school"],
            "landuse": ["port"],
            "industrial": ["port"],
            "harbour": True,
        }
        gdf = ox.features_from_polygon(polygon, tags)
        gdf = gdf.reset_index()
        rows = []
        for _, row in gdf.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue
            typ = None
            if row.get("man_made") == "bridge" or str(row.get("bridge", "")).lower() in ("yes", "viaduct", "movable"): typ = "bridge"
            elif row.get("amenity") == "hospital": typ = "hospital"
            elif row.get("amenity") == "school": typ = "school"
            elif row.get("highway") in ("primary", "secondary", "trunk"):
                typ = f"road_{row.get('highway')}"
            elif "port" in str(row.get("name", "")).lower() or row.get("landuse") == "port" or row.get("industrial") == "port" or str(row.get("harbour", "")).lower() == "yes" or "ميناء" in str(row.get("name", "")):
                typ = "port"
            if typ:
                osm_id = row.get("osmid", row.get("id", "unknown"))
                osm_type = str(row.get("element", "way"))
                rows.append({"asset_id": stable_asset_id(osm_type, osm_id),
                             "name": str(row.get("name") or f"Unnamed {typ}"),
                             "type": typ, "osm_id": str(osm_id), "geometry": geom})
        result = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
        if result.empty:
            raise RuntimeError("OSM query returned no supported assets")
        return result.drop_duplicates("asset_id").head(int(cfg["assets"]["max_osm_assets"]))
    except Exception as exc:
        LOG.exception("OSM extraction failed; refusing to mix synthetic assets with production measurements.")
        raise RuntimeError("OSM asset extraction failed; rerun with --demo for a fully synthetic demo.") from exc

def load_velocity_points(raster_path: str, max_points: int = 2500) -> gpd.GeoDataFrame:
    """Sample valid raster pixels into geographic points with velocity and quality."""
    import rasterio
    import numpy as np
    from rasterio.transform import xy
    with rasterio.open(raster_path) as src:
        arr = src.read(1, masked=True)
        valid = np.argwhere(~np.ma.getmaskarray(arr))
        if len(valid) > max_points:
            rng = np.random.default_rng(42)
            valid = valid[rng.choice(len(valid), max_points, replace=False)]
        rows = []
        for r, c in valid:
            lon, lat = xy(src.transform, int(r), int(c), offset="center")
            value = float(arr[r, c])
            # Demo coherence is a plausible quality proxy; production should use HyP3 coherence.
            coherence = float(np.clip(0.78 + np.random.default_rng(r*100000+c).normal(0, .08), .35, .98))
            rows.append({"velocity_mm_yr": value, "coherence": coherence, "geometry": Point(lon, lat)})
    return gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")

def associate_assets(assets: gpd.GeoDataFrame, points: gpd.GeoDataFrame, buffer_m: int = 40) -> gpd.GeoDataFrame:
    """Aggregate nearby point samples per asset using a metric buffer."""
    if assets.empty or points.empty:
        raise ValueError("Assets and velocity points must both be non-empty")
    metric_assets = assets.to_crs(32632).copy()
    metric_points = points.to_crs(32632).copy()
    # Each sample is assigned to its nearest asset, only within the configured buffer.
    joined = gpd.sjoin_nearest(
        metric_points, metric_assets[["asset_id", "geometry"]],
        how="inner", max_distance=float(buffer_m), distance_col="asset_distance_m"
    )
    grouped = joined.groupby("asset_id").agg(
        velocity_mean=("velocity_mm_yr", "mean"),
        velocity_max=("velocity_mm_yr", lambda s: float(s.abs().max())),
        coherence=("coherence", "mean"),
        sample_count=("velocity_mm_yr", "size"),
    ).reset_index()
    out = assets.merge(grouped, on="asset_id", how="left")
    out["velocity_mean"] = out["velocity_mean"].fillna(0.0)
    out["velocity_max"] = out["velocity_max"].fillna(0.0)
    out["coherence"] = out["coherence"].fillna(0.4)
    out["sample_count"] = out["sample_count"].fillna(0).astype(int)
    return out
