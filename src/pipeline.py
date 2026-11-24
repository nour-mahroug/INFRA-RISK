from __future__ import annotations
import argparse, logging
from .real_pipeline import run_real

def main() -> None:
    parser = argparse.ArgumentParser(description="INFRA-RISK Tunisia pipeline (real data only)")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--raster", default="data/processed/velocity_real.tif")
    parser.add_argument("--out", default="outputs/real")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run_real(args.config, args.raster, args.out)   # fails loudly if data/OSM are missing

if __name__ == "__main__":
    main()
