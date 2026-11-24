"""InSAR velocity analysis, including deterministic demo raster generation."""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Any
import numpy as np

LOG = logging.getLogger(__name__)

def create_demo_velocity(cfg: dict[str, Any], output_path: str | Path | None = None) -> dict[str, Any]:
    """Create a seeded, synthetic LOS velocity raster with planted spatial hotspots."""
    import rasterio
    from rasterio.transform import from_bounds
    west, south, east, north = cfg["aoi"]["bbox"]
    n = int(cfg["insar"].get("demo_points", 1800))
    width = max(80, int(np.sqrt(n) * 1.5))
    height = max(80, int(np.sqrt(n)))
    rng = np.random.default_rng(int(cfg["insar"]["demo_seed"]))
    y, x = np.mgrid[0:height, 0:width]
    field = rng.normal(0.0, 1.1, (height, width))
    # Smooth spatial component plus planted deformation-like lobes.
    field += 0.7 * np.sin(x / 13.0) + 0.45 * np.cos(y / 17.0)
    hotspots = [
        (int(height*.28), int(width*.72), 7.5, 8),
        (int(height*.62), int(width*.38), -6.5, 10),
        (int(height*.76), int(width*.78), 5.8, 7),
    ]
    for cy, cx, amplitude, sigma in hotspots:
        field += amplitude * np.exp(-((x-cx)**2 + (y-cy)**2) / (2*sigma**2))
    path = Path(output_path or cfg["paths"]["velocity_raster"])
    path.parent.mkdir(parents=True, exist_ok=True)
    transform = from_bounds(west, south, east, north, width, height)
    with rasterio.open(path, "w", driver="GTiff", height=height, width=width,
                       count=1, dtype="float32", crs="EPSG:4326",
                       transform=transform, nodata=-9999.0) as dst:
        dst.write(field.astype("float32"), 1)
    LOG.warning("SYNTHETIC DEMO DATA written to %s; not satellite-derived.", path)
    return {"path": str(path), "mode": "demo", "source": "SYNTHETIC_DEMO",
            "shape": [height, width], "hotspots": len(hotspots)}

def load_hyp3_products(cfg: dict[str, Any], jobs: list[Any]) -> list[str]:
    """Download completed HyP3 products and return local product paths."""
    if not jobs:
        raise RuntimeError("No HyP3 jobs supplied")
    import hyp3_sdk
    api_key = __import__("os").getenv("HYP3_API_KEY")
    client = hyp3_sdk.HyP3(api_key=api_key)
    job_ids = [job.jobs[0]["job_id"] for job in jobs if getattr(job, "jobs", None)]
    statuses = client.watch(job_ids, timeout=0, interval=60)
    directory = Path(cfg["paths"]["raw"]); directory.mkdir(parents=True, exist_ok=True)
    downloaded = statuses.download_files(str(directory))
    return [str(p) for p in downloaded]

def run_mintpy_hyp3(cfg: dict[str, Any], product_paths: list[str]) -> dict[str, Any]:
    """Prepare/run MintPy's HyP3 SBAS workflow from downloaded products.

    MintPy's command-line workflow and template requirements vary by product release.
    This adapter writes a minimal template and invokes smallbaselineApp; users should
    inspect the generated template and reference-point choice for production use.
    """
    if not product_paths:
        raise RuntimeError("No downloaded HyP3 products")
    import subprocess
    work = Path(cfg["paths"]["processed"]) / "mintpy"
    work.mkdir(parents=True, exist_ok=True)
    template = work / "smallbaselineApp.cfg"
    template.write_text(
        "## MintPy small-baseline configuration\n"
        "mintpy.load.processor = hyp3\n"
        f"mintpy.network.coherenceBased = yes\n"
        f"mintpy.network.coherenceThreshold = {cfg['insar']['coherence_threshold']}\n"
        "mintpy.reference.lalo = auto\n"
        "mintpy.compute.maxMemory = 4\n", encoding="utf-8")
    # HyP3 products are ingested by MintPy's prep_hyp3.py helper.
    subprocess.run(["prep_hyp3.py", *product_paths, "-d", str(work)], check=True)
    subprocess.run(["smallbaselineApp.py", str(template), "--dostep", "velocity"], cwd=work, check=True)
    candidates = list(work.rglob("velocity.h5"))
    if not candidates:
        raise RuntimeError("MintPy completed but velocity.h5 was not found")
    return {"mode": "production", "velocity_h5": str(candidates[0]),
            "note": "Export the velocity dataset to GeoTIFF for the asset sampler."}

def analyze(cfg: dict[str, Any], collection: dict[str, Any], demo: bool = False) -> dict[str, Any]:
    """Create demo raster or process HyP3 products with MintPy."""
    if demo or collection.get("mode") == "demo":
        return create_demo_velocity(cfg)
    products = load_hyp3_products(cfg, collection["jobs"])
    result = run_mintpy_hyp3(cfg, products)
    return result
