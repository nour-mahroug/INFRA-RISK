
from __future__ import annotations
import logging
import numpy as np

LOG = logging.getLogger(__name__)


def background_median(xy: np.ndarray, vel: np.ndarray, query_xy: np.ndarray,
                      radius_m: float = 1500.0, min_pixels: int = 20) -> np.ndarray:
    """Median of `vel` over the pixels within radius_m of each query point (NaN if too few pixels)."""
    from scipy.spatial import cKDTree
    tree = cKDTree(xy)
    out = np.full(len(query_xy), np.nan)
    for i, idx in enumerate(tree.query_ball_point(query_xy, r=radius_m)):
        if len(idx) >= min_pixels:
            out[i] = np.median(vel[idx])
    return out


def to_relative(measured, points, radius_m: float = 1500.0, min_pixels: int = 20):
    """Return a copy of `measured` where velocity_mean is relative to the neighbourhood.

    Adds velocity_abs (original LOS velocity), velocity_background and velocity_rel. The caller
    must set velocity_mean back to velocity_abs after scoring so that reports show the real LOS value.
    """
    import geopandas as gpd
    pts = points.to_crs(32632)
    xy = np.column_stack([pts.geometry.x.to_numpy(), pts.geometry.y.to_numpy()])
    vel = points["velocity_mm_yr"].to_numpy(dtype=float)
    crs = measured.crs or "EPSG:4326"
    reps = gpd.GeoSeries(measured.geometry.representative_point(), crs=crs).to_crs(32632)
    query = np.column_stack([reps.x.to_numpy(), reps.y.to_numpy()])
    bg = background_median(xy, vel, query, radius_m, min_pixels)
    missing = ~np.isfinite(bg)
    if missing.any():
        LOG.warning("%d assets have fewer than %d pixels within %.0f m; using the global median.",
                    int(missing.sum()), min_pixels, radius_m)
        bg[missing] = float(np.median(vel))
    out = measured.copy()
    out["velocity_abs"] = out["velocity_mean"].astype(float)
    out["velocity_background"] = bg
    out["velocity_rel"] = out["velocity_abs"] - bg
    out["velocity_mean"] = out["velocity_rel"]   # scored on the relative velocity
    return out