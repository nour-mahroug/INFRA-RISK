from __future__ import annotations
import argparse, copy, logging
from pathlib import Path
import pandas as pd

from .config import load_config
from .assets import extract_osm_assets, associate_assets
from .anomalies import score_assets
from .real_pipeline import load_real_points, _clean_names
from .neighbourhood import to_relative

LOG = logging.getLogger(__name__)
TOP_N = 20


def _run(cfg, assets, points, buffer_m, min_coherence, radius_m=1500.0):
    """Same ranking rules as the real pipeline: >= min_samples radar pixels per asset."""
    pts = points[points["coherence"] >= min_coherence]
    if pts.empty:
        return None
    min_samples = int(cfg["assets"].get("min_samples", 3))
    assoc = associate_assets(assets, pts, buffer_m)
    measured = assoc[assoc["sample_count"] >= min_samples].copy()
    return score_assets(to_relative(measured, pts, radius_m), cfg) if not measured.empty else None


def main() -> None:
    parser = argparse.ArgumentParser(description="INFRA-RISK sensitivity analysis")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--raster", default="data/processed/velocity_real.tif")
    parser.add_argument("--out", default="outputs/real/sensitivity.csv")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config(args.config)
    points, _ = load_real_points(args.raster)
    assets = _clean_names(extract_osm_assets(cfg, demo=False))
    min_samples = int(cfg["assets"].get("min_samples", 3))
    base_cov = float(cfg["insar"]["coherence_threshold"])
    base = _run(cfg, assets, points, 60, base_cov)
    if base is None:
        raise SystemExit("Baseline run produced no measured asset.")
    base_rank = base.set_index("asset_id")["rank"]
    base_top = set(base.nsmallest(TOP_N, "rank")["asset_id"])
    rows = []

    def record(label, frame):
        if frame is None:
            rows.append({"variant": label, "assets": 0, "flagged": 0, "top20_overlap": None,
                         "spearman_vs_baseline": None})
            return
        top = set(frame.nsmallest(TOP_N, "rank")["asset_id"])
        joined = pd.concat([base_rank.rename("base"), frame.set_index("asset_id")["rank"].rename("var")],
                           axis=1, join="inner")
        rho = joined["base"].corr(joined["var"], method="spearman") if len(joined) > 2 else None
        rows.append({"variant": label, "assets": len(frame), "flagged": int(frame["is_anomaly"].sum()),
                     "top20_overlap": len(base_top & top), "spearman_vs_baseline": rho})

    record(f"baseline (buffer 60 m, min {min_samples} pixels, z 2.5, contamination 0.10)", base)
    for buf in (80, 100):
        record(f"buffer {buf} m", _run(cfg, assets, points, buf, base_cov))
    for coh in (base_cov + 0.10, base_cov + 0.20):
        record(f"min coherence {coh:.2f}", _run(cfg, assets, points, 60, coh))
    for rad in (1000.0, 2500.0):
        record(f"neighbourhood radius {rad:.0f} m", _run(cfg, assets, points, 60, base_cov, rad))
    for z in (2.0, 3.0):
        c = copy.deepcopy(cfg); c["anomaly"]["robust_z_threshold"] = z
        record(f"robust z threshold {z}", _run(c, assets, points, 60, base_cov))
    for cont in (0.05, 0.15):
        c = copy.deepcopy(cfg); c["anomaly"]["isolation_contamination"] = cont
        record(f"isolation contamination {cont}", _run(c, assets, points, 60, base_cov))
    table = pd.DataFrame(rows)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(args.out, index=False)
    print(table.to_string(index=False, float_format=lambda v: f"{v:.2f}"))
    print(f"\nWrote {args.out}. Top-{TOP_N} overlap shows how stable the shortlist is; "
          "Spearman covers all assets.")


if __name__ == "__main__":
    main()