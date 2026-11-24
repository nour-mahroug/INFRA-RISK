"""Tests for robust anomaly scoring and risk output."""
import numpy as np
import pandas as pd
from src.anomalies import robust_z_scores, score_assets

def test_robust_z_scores_detects_outlier():
    values = np.array([0., .1, -.1, .05, 8.])
    scores = robust_z_scores(values)
    assert scores[-1] > 2.5
    assert scores[0] < 2.5

def test_score_assets_has_bounded_scores_and_ranks():
    cfg = {"anomaly":{"mad_scale":1.4826,"robust_z_threshold":2.5,
                      "isolation_contamination":.1,"random_state":42},
           "risk":{"weights":{"velocity":.35,"anomaly":.30,"importance":.20,"quality":.15},
                   "importance":{"bridge":1.0,"hospital":.9,"road_primary":.8}}}
    frame = pd.DataFrame({
        "asset_id":[f"a{i}" for i in range(12)],
        "type":["bridge","hospital","road_primary"]*4,
        "velocity_mean":[0,.1,-.1,.05,.2,-.2,.1,0,.15,-.1,.2,8.0],
        "velocity_max":[.1,.2,.2,.1,.3,.3,.2,.1,.2,.2,.3,9.0],
        "coherence":[.8]*12,
    })
    result = score_assets(frame, cfg)
    assert result["risk_score"].between(0,100).all()
    assert sorted(result["rank"].tolist()) == list(range(1,13))
    assert result["is_anomaly"].dtype == bool
