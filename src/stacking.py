from __future__ import annotations
import argparse, logging, re, warnings, zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
import numpy as np
import warnings
warnings.filterwarnings("ignore", message="Mean of empty slice", category=RuntimeWarning)
from .config import load_config

LOG = logging.getLogger(__name__)
PAIR_RE = re.compile(r"_(\d{8})T\d{6}_(\d{8})T\d{6}_")
SOURCE_TAG = "Sentinel-1 / HyP3 / stacking"
warnings.filterwarnings("ignore", message="Mean of empty slice", category=RuntimeWarning)


def parse_pair_dates(name: str) -> tuple[datetime, datetime]:
    """Read the two acquisition dates from a HyP3 product name."""
    match = PAIR_RE.search(name)
    if not match:
        raise ValueError(f"Cannot read dates from product name: {name}")
    return tuple(datetime.strptime(d, "%Y%m%d") for d in match.groups())  # type: ignore[return-value]


def stack_pairs(disp_m: np.ndarray, corr: np.ndarray, years: np.ndarray, *, coh_threshold: float = 0.35,
                min_pairs: int = 5, ref_mask: np.ndarray | None = None, ref_fraction: float = 0.02) -> dict[str, Any]:
    """Estimate velocity (mm/yr) per pixel from pair displacements.

    disp_m: (n_pairs, h, w) LOS displacement in metres; corr: same shape, coherence 0-1;
    years: (n_pairs,) elapsed time of each pair in years.
    """
    disp = np.where(np.isfinite(disp_m) & np.isfinite(corr) & (corr >= coh_threshold), disp_m, np.nan)
    n_pairs = disp.shape[0]
    valid_count = np.sum(np.isfinite(disp), axis=0)
    mean_coh = np.nanmean(np.where(np.isfinite(disp), corr, np.nan), axis=0)
    if ref_mask is None:
        # Default stable reference: the most coherent pixels that are valid in most pairs.
        candidates = valid_count >= max(min_pairs, int(0.8 * n_pairs))
        if not candidates.any():
            raise RuntimeError("No pixel is valid in enough pairs to choose a reference area.")
        cutoff = np.nanquantile(mean_coh[candidates], 1 - ref_fraction)
        ref_mask = candidates & (mean_coh >= cutoff)
    keep = []
    for i in range(n_pairs):
        sample = disp[i][ref_mask]
        sample = sample[np.isfinite(sample)]
        if sample.size == 0:
            LOG.warning("Pair %d has no valid pixel in the reference area; dropped.", i)
            continue
        disp[i] = disp[i] - np.median(sample)
        keep.append(i)
    disp, years = disp[keep], np.asarray(years, dtype=float)[keep]
    t = years[:, None, None]
    ok = np.isfinite(disp)
    num = np.nansum(np.where(ok, t * disp, 0.0), axis=0)
    den = np.sum(np.where(ok, t * t, 0.0), axis=0)
    n = ok.sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        velocity = num / den
        resid = np.where(ok, disp - velocity * t, 0.0)
        sigma = np.sqrt(np.sum(resid ** 2, axis=0) / np.maximum(n - 1, 1))
        stderr = sigma / np.sqrt(den)
    bad = (n < min_pairs) | (den <= 0)
    velocity = np.where(bad, np.nan, velocity * 1000.0)
    stderr = np.where(bad, np.nan, stderr * 1000.0)
    mean_coh = np.where(bad, np.nan, np.nanmean(np.where(ok, corr[keep], np.nan), axis=0))
    return {"velocity_mm_yr": velocity, "coherence": mean_coh, "stderr_mm_yr": stderr,
            "n_pairs_used": n, "pairs_kept": len(keep), "ref_pixels": int(ref_mask.sum())}


def _extract(zip_path: Path, work: Path) -> dict[str, Path]:
    """Extract the displacement and coherence rasters of one HyP3 product."""
    wanted = {}
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.namelist():
            for key, suffix in (("disp", "_los_disp.tif"), ("phase", "_unw_phase.tif"), ("corr", "_corr.tif")):
                if member.endswith(suffix):
                    target = work / Path(member).name
                    if not target.exists():
                        target.write_bytes(archive.read(member))
                    wanted[key] = target
    return wanted


def _to_grid(path: Path, transform, width: int, height: int) -> np.ndarray:
    """Resample one raster onto the common WGS84 grid (NaN where there is no data)."""
    import rasterio
    from rasterio.warp import reproject, Resampling
    out = np.full((height, width), np.nan, dtype="float32")
    with rasterio.open(path) as src:
        reproject(source=rasterio.band(src, 1), destination=out, src_transform=src.transform,
                  src_crs=src.crs, src_nodata=src.nodata if src.nodata is not None else 0,
                  dst_transform=transform, dst_crs="EPSG:4326", dst_nodata=np.nan,
                  resampling=Resampling.bilinear)
    return out


def build_velocity(cfg: dict[str, Any], raw_dir: Path, out_path: Path, res_deg: float = 0.0008,
                   ref_lonlat: tuple[float, float] | None = None, ref_radius_deg: float = 0.003,
                   min_pairs: int = 5) -> Path:
    """Read all downloaded HyP3 products and write the velocity GeoTIFF."""
    import rasterio
    from rasterio.transform import from_bounds
    west, south, east, north = cfg["aoi"]["bbox"]
    width, height = int(round((east - west) / res_deg)), int(round((north - south) / res_deg))
    transform = from_bounds(west, south, east, north, width, height)
    work = out_path.parent / "hyp3_extract"
    work.mkdir(parents=True, exist_ok=True)
    disp_list, corr_list, years, starts, ends = [], [], [], [], []
    for zip_path in sorted(raw_dir.glob("*.zip")):
        try:
            d1, d2 = parse_pair_dates(zip_path.name)
            files = _extract(zip_path, work)
            if "corr" not in files or ("disp" not in files and "phase" not in files):
                LOG.warning("%s: missing displacement or coherence file, skipped", zip_path.name)
                continue
            if "disp" in files:
                disp = _to_grid(files["disp"], transform, width, height)
            else:  # fallback: convert unwrapped phase (rad) to metres, Sentinel-1 wavelength 5.5465763 cm
                LOG.warning("%s: no los_disp file, converting unw_phase", zip_path.name)
                disp = _to_grid(files["phase"], transform, width, height) * 0.055465763 / (-4 * np.pi)
            corr = _to_grid(files["corr"], transform, width, height)
        except Exception:
            LOG.exception("Skipping %s", zip_path.name)
            continue
        disp_list.append(disp); corr_list.append(corr)
        years.append(abs((d2 - d1).days) / 365.25)
        starts.append(min(d1, d2)); ends.append(max(d1, d2))
    if len(disp_list) < min_pairs:
        raise SystemExit(f"Only {len(disp_list)} usable products in {raw_dir}; need at least {min_pairs}.")
    ref_mask = None
    if ref_lonlat:
        lon, lat = ref_lonlat
        cols = west + (np.arange(width) + 0.5) * res_deg
        rows = north - (np.arange(height) + 0.5) * ((north - south) / height)
        lon_g, lat_g = np.meshgrid(cols, rows)
        ref_mask = (lon_g - lon) ** 2 + (lat_g - lat) ** 2 <= ref_radius_deg ** 2
        if not ref_mask.any():
            raise SystemExit("The reference point is outside the area or has no pixel.")
    result = stack_pairs(np.stack(disp_list), np.stack(corr_list), np.array(years),
                         coh_threshold=float(cfg["insar"]["coherence_threshold"]),
                         min_pairs=min_pairs, ref_mask=ref_mask)
    arrays = [np.where(np.isfinite(result[k]), result[k], -9999.0).astype("float32")
              for k in ("velocity_mm_yr", "coherence", "stderr_mm_yr")]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out_path, "w", driver="GTiff", height=height, width=width, count=3,
                       dtype="float32", crs="EPSG:4326", transform=transform, nodata=-9999.0) as dst:
        for index, array in enumerate(arrays, start=1):
            dst.write(array, index)
        dst.set_band_description(1, "LOS velocity mm/yr")
        dst.set_band_description(2, "mean coherence")
        dst.set_band_description(3, "velocity standard error mm/yr")
        dst.update_tags(SOURCE=SOURCE_TAG, OBS_START=min(starts).date().isoformat(),
                        OBS_END=max(ends).date().isoformat(), N_PAIRS=str(result["pairs_kept"]),
                        REFERENCE=("lon/lat %s" % (ref_lonlat,)) if ref_lonlat else "auto: most coherent 2% of pixels",
                        SIGN="positive = toward satellite (HyP3 los_disp convention)")
    vel = result["velocity_mm_yr"][np.isfinite(result["velocity_mm_yr"])]
    LOG.info("Pairs used: %d | valid pixels: %d (%.0f%%) | median velocity %.2f mm/yr | 5-95%%: %.1f to %.1f mm/yr",
             result["pairs_kept"], vel.size, 100 * vel.size / (width * height), np.median(vel),
             np.percentile(vel, 5), np.percentile(vel, 95))
    _quicklook(result["velocity_mm_yr"], out_path.with_suffix(".png"), (west, east, south, north))
    return out_path


def _quicklook(velocity: np.ndarray, png_path: Path, extent: tuple[float, float, float, float]) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    limit = float(np.nanpercentile(np.abs(velocity), 98)) or 1.0
    fig, ax = plt.subplots(figsize=(7, 6))
    image = ax.imshow(velocity, cmap="RdBu", vmin=-limit, vmax=limit, extent=extent)
    fig.colorbar(image, label="LOS velocity (mm/yr)")
    ax.set_title("Sentinel-1 / HyP3 stacking: LOS velocity")
    fig.savefig(png_path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Stack HyP3 interferograms into a velocity map")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--ref", default=None, help="stable reference as lon,lat (default: automatic)")
    parser.add_argument("--min-pairs", type=int, default=5)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config(args.config)
    ref = tuple(float(v) for v in args.ref.split(",")) if args.ref else None
    out = build_velocity(cfg, Path(cfg["paths"]["raw"]), Path(cfg["paths"]["processed"]) / "velocity_real.tif",
                         ref_lonlat=ref, min_pairs=args.min_pairs)  # type: ignore[arg-type]
    print("Wrote", out, "and", out.with_suffix(".png"))


if __name__ == "__main__":
    main()
