"""Defensible anomaly consensus and transparent 0–100 risk scoring."""
from __future__ import annotations
import logging
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

LOG = logging.getLogger(__name__)

def robust_z_scores(values: pd.Series | np.ndarray, mad_scale: float = 1.4826) -> np.ndarray:
    """Compute absolute robust z-scores using median and median absolute deviation."""
    arr = np.asarray(values, dtype=float)
    median = np.nanmedian(arr)
    mad = np.nanmedian(np.abs(arr - median))
    if not np.isfinite(mad) or mad < 1e-9:
        return np.zeros_like(arr, dtype=float)
    return np.abs((arr - median) / (mad_scale * mad))

def score_assets(frame: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Flag only consensus anomalies and compute documented weighted risk scores."""
    if frame.empty:
        return frame.copy()
    result = frame.copy()
    values = result["velocity_mean"].fillna(0).to_numpy(dtype=float)
    z = robust_z_scores(values, float(cfg["anomaly"]["mad_scale"]))
    threshold = float(cfg["anomaly"]["robust_z_threshold"])
    robust_flag = z >= threshold
    features = np.column_stack([values, result["velocity_max"].fillna(0), result["coherence"].fillna(.4)])
    if len(result) >= 4 and np.nanstd(features[:, 0]) > 1e-9:
        model = IsolationForest(
            contamination=float(cfg["anomaly"]["isolation_contamination"]),
            random_state=int(cfg["anomaly"]["random_state"]),
        )
        iso_flag = model.fit_predict(features) == -1
    else:
        iso_flag = np.zeros(len(result), dtype=bool)
    result["robust_z"] = z
    result["robust_flag"] = robust_flag
    result["isolation_flag"] = iso_flag
    result["is_anomaly"] = robust_flag & iso_flag

    # Normalize absolute motion to a 0–1 scale; 15 mm/yr is a configurable screening cap.
    velocity_norm = np.clip(np.abs(values) / 15.0, 0, 1)
    anomaly_norm = np.clip(z / max(threshold * 2.0, 1.0), 0, 1)
    importance_map = cfg["risk"]["importance"]
    importance = result["type"].map(importance_map).fillna(.5).to_numpy(dtype=float)
    quality = np.clip(result["coherence"].fillna(.4).to_numpy(dtype=float), 0, 1)
    weights = cfg["risk"]["weights"]
    score = 100 * (
        float(weights["velocity"]) * velocity_norm
        + float(weights["anomaly"]) * anomaly_norm
        + float(weights["importance"]) * importance
        + float(weights["quality"]) * quality
    )
    # Consensus is the alert gate, not a multiplier that hides the continuous ranking.
    result["risk_score"] = np.round(score, 2)
    result["priority"] = np.where(result["is_anomaly"], "high",
                         np.where(result["risk_score"] >= 55, "medium", "low"))
    result = result.sort_values(["is_anomaly", "risk_score"], ascending=[False, False]).reset_index(drop=True)
    result["rank"] = np.arange(1, len(result) + 1)
    LOG.info("Anomaly consensus: %d/%d assets flagged", int(result["is_anomaly"].sum()), len(result))
    return result
