from __future__ import annotations
import logging
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator
from .config import load_config
from .real_pipeline import ScreeningError, raster_window, screen_area

LOG = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config.yaml"
RASTER = ROOT / "data" / "processed" / "velocity_real.tif"
TUNISIA = (7.5, 30.0, 11.7, 37.6)   # west, south, east, north
app = FastAPI(title="INFRA-RISK Tunisia API", version="2.1.0",
              description="Live infrastructure screening from Sentinel-1. Screening, not failure prediction.")


class ScreenRequest(BaseModel):
    model_config = {"json_schema_extra": {"examples": [
        {"area": [10.10, 36.74, 10.34, 36.86], "start_date": "2024-07-09", "end_date": "2025-06-04"}
    ]}}

    area: list[float] = Field(..., min_length=4, max_length=4, description="[west, south, east, north]")
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def check(self):
        w, s, e, n = self.area
        if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
            raise ValueError("area must be [west, south, east, north] with west < east and south < north")
        tw, ts, te, tn = TUNISIA
        if w < tw or e > te or s < ts or n > tn:
            raise ValueError(f"area must lie inside Tunisia (lon {tw} to {te}, lat {ts} to {tn})")
        if (e - w) * (n - s) > 0.1:
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
        tags = raster_window(str(RASTER))        # cheap: checked BEFORE the heavy OSM + scoring step
        obs_start, obs_end = tags.get("OBS_START"), tags.get("OBS_END")
        if obs_start and obs_end and (req.start_date.isoformat() > obs_end or req.end_date.isoformat() < obs_start):
            raise ScreeningError(f"Requested period does not overlap the observed window {obs_start} to {obs_end}.")
        return _cached(tuple(req.area), RASTER.stat().st_mtime)
    except ScreeningError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    except Exception as exc:
        LOG.exception("screen failed")
        raise HTTPException(500, "Internal error while screening; see server log.") from exc