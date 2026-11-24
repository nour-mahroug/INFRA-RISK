"""Sentinel-1 discovery and ASF HyP3 job submission."""
from __future__ import annotations
import logging, os
from typing import Any
from pathlib import Path

LOG = logging.getLogger(__name__)

def search_scenes(cfg: dict[str, Any]) -> list[Any]:
    """Search Sentinel-1 IW SLC scenes using ASF Search."""
    try:
        import asf_search as asf
        west, south, east, north = cfg["aoi"]["bbox"]
        results = asf.search(
            platform=[asf.PLATFORM.SENTINEL1],
            processingLevel=[asf.PRODUCT_TYPE.SLC],
            beamMode=[asf.BEAMMODE.IW],
            intersects=f"POLYGON(({west} {south},{east} {south},{east} {north},{west} {north},{west} {south}))",
            start=cfg["dates"]["start"], end=cfg["dates"]["end"],
            flightDirection=cfg["insar"]["orbit_direction"],
        )
        scenes = list(results)[: int(cfg["insar"]["max_scenes"])]
        LOG.info("ASF returned %d Sentinel-1 SLC scenes", len(scenes))
        return scenes
    except Exception:
        LOG.exception("Sentinel-1 discovery failed")
        raise

def build_pairs(scenes: list[Any], max_pairs: int) -> list[tuple[Any, Any]]:
    """Build a short-baseline network pairing each scene with up to two successors."""
    pairs = []
    ordered = sorted(scenes, key=lambda item: str(item.properties.get("startTime", "")))
    for index, scene in enumerate(ordered):
        for successor in ordered[index + 1:index + 3]:
            pairs.append((scene, successor))
            if len(pairs) >= max_pairs:
                return pairs
    return pairs

def submit_hyp3_jobs(scenes: list[Any], cfg: dict[str, Any]) -> list[Any]:
    """Submit HyP3 InSAR jobs; requires HYP3_API_KEY and ASF credentials."""
    api_key = os.getenv("HYP3_API_KEY")
    if not api_key:
        raise RuntimeError("HYP3_API_KEY is not configured")
    try:
        import hyp3_sdk
        client = hyp3_sdk.HyP3(api_key=api_key)
        pairs = build_pairs(scenes, int(cfg["insar"]["max_pairs"]))
        jobs = []
        for first, second in pairs:
            p1, p2 = first.properties, second.properties
            jobs.append(client.submit_insar_job(
                granule1=p1["sceneName"], granule2=p2["sceneName"],
                name=f"infra-risk-{p1['sceneName'][:12]}-{p2['sceneName'][:12]}",
                apply_water_mask=True,
            ))
        LOG.info("Submitted %d HyP3 InSAR jobs", len(jobs))
        return jobs
    except Exception:
        LOG.exception("HyP3 job submission failed")
        raise

def collect(cfg: dict[str, Any], demo: bool = False) -> dict[str, Any]:
    """Run scene discovery and optionally submit cloud jobs."""
    if demo:
        LOG.warning("DEMO MODE: skipping ASF discovery and HyP3 submission.")
        return {"mode": "demo", "scenes": [], "jobs": []}
    scenes = search_scenes(cfg)
    if len(scenes) < 3:
        raise RuntimeError("Fewer than three scenes found; cannot form an SBAS network")
    jobs = submit_hyp3_jobs(scenes, cfg)
    return {"mode": "production", "scenes": scenes, "jobs": jobs}
