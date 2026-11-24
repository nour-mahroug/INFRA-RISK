from __future__ import annotations
import logging
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator
from .config import load_config
from .real_pipeline import screen_area

LOG = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config.yaml"
RASTER = ROOT / "data" / "processed" / "velocity_real.tif"
app = FastAPI(title="INFRA-RISK Tunisia API", version="2.0.0",
              description="Live infrastructure screening from Sentinel-1. Screening, not failure prediction.")

class ScreenRequest(BaseModel):
    area: list[float] = Field(..., min_length=4, max_length=4, description="[west, south, east, north]")
    start_date: date
    end_date: date
    @model_validator(mode="after")
    def check(self):
        w, s, e, n = self.area
        if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
            raise ValueError("area must be a valid [west,south,east,north] bbox")
        if (e - w) * (n - s) > 0.1:   # ~ >30x30 km: protects Overpass and the server
            raise ValueError("area too large (max about 0.1 square degrees)")
        if self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        return self

@lru_cache(maxsize=16)
def _cached(bbox: tuple, raster_mtime: float) -> dict[str, Any]:
    return screen_area(load_config(CONFIG), list(bbox), str(RASTER))

@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "raster_present": RASTER.exists(), "positioning": "screening_not_prediction"}

@app.post("/screen")
def screen(req: ScreenRequest) -> dict[str, Any]:
    if not RASTER.exists():
        raise HTTPException(503, "No real velocity raster yet: run hyp3_jobs + stacking first.")
    try:
        result = _cached(tuple(req.area), RASTER.stat().st_mtime)
    except SystemExit as exc:          # raster not tagged Sentinel-1, or nothing measured
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        LOG.exception("screen failed")
        raise HTTPException(500, str(exc)) from exc
    meta = result["metadata"]
    if req.start_date.isoformat() > meta["obs_end"] or req.end_date.isoformat() < meta["obs_start"]:
        raise HTTPException(422, f"Requested period does not overlap the observed window "
                                 f"{meta['obs_start']} to {meta['obs_end']}.")
    return result
