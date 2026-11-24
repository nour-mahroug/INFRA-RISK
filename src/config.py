from __future__ import annotations
from pathlib import Path
from typing import Any
import logging
import yaml

LOG = logging.getLogger(__name__)

def load_config(path: str | Path = "config.yaml") -> dict[str, Any]:
    """Load YAML configuration and validate essential settings."""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as stream:
        cfg = yaml.safe_load(stream) or {}
    bbox = cfg.get("aoi", {}).get("bbox", [])
    if len(bbox) != 4 or not (bbox[0] < bbox[2] and bbox[1] < bbox[3]):
        raise ValueError("aoi.bbox must be [west, south, east, north]")
    start, end = cfg.get("dates", {}).get("start"), cfg.get("dates", {}).get("end")
    if not start or not end or start > end:
        raise ValueError("Invalid date range in configuration")
    weights = cfg.get("risk", {}).get("weights", {})
    if weights and abs(sum(float(v) for v in weights.values()) - 1.0) > 1e-6:
        raise ValueError("Risk weights must sum to 1.0")
    LOG.info("Loaded configuration from %s", config_path)
    return cfg

def ensure_directories(cfg: dict[str, Any]) -> None:
    """Create configured data and output directories."""
    for key in ("raw", "processed", "outputs"):
        Path(cfg["paths"][key]).mkdir(parents=True, exist_ok=True)
