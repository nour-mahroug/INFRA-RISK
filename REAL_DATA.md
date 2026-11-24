# Real-data path (Sentinel-1 + ASF HyP3)

Run everything from the inner project folder, with `(.venv)` active.

## 0. One-time setup
1. Copy `.env.example` to a new file named `.env` and fill in ASF_USERNAME and ASF_PASSWORD
   with your NASA Earthdata login. Never share or commit this file (it is in .gitignore).
2. `pip install -r requirements-real.txt`

## 1. Plan, then submit (cloud processing takes hours)
    python -m src.hyp3_jobs plan
    python -m src.hyp3_jobs submit
`plan` only searches and prints the scenes and pairs. `submit` asks you to type YES first.
Default: 12 monthly scenes between 2024-07-01 and 2025-06-30 on one track, 2 neighbours per scene
(about 21 pairs). Options: `--start`, `--end`, `--months`, `--direction`.

## 2. Follow the jobs and download
    python -m src.hyp3_jobs status
    python -m src.hyp3_jobs download
Run `download` again later to fetch jobs that finished after the first run. Files go to data/raw.

## 3. Build the velocity map
    python -m src.stacking
Writes data/processed/velocity_real.tif (velocity, coherence, standard error) and a .png quick look.
Check the printed median velocity: on stable ground it should be close to 0 mm/yr.
Optional stable reference: `--ref lon,lat`.

## 4. Run the pipeline on real assets (needs internet for OpenStreetMap)
    python -m src.real_pipeline
Outputs: outputs/real/alerts.geojson, map.html, ranked_assets.csv (the demo outputs stay untouched).

## What this is, and is not
- Method: stacking of pair displacements (least-squares slope), referenced to a stable area. It is
  simpler than MintPy's SBAS inversion; say so in the presentation.
- Sign: positive = toward the satellite, negative = away (HyP3 los_disp convention; verify for your product version).
- Overlapping pairs are correlated, so the standard error band is optimistic.
- About one year of data gives a few mm/yr of uncertainty: only clear movement is meaningful.
- Assets with no reliable pixel are not reported. A high score means "inspect sooner", never "will fail".
