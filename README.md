# INFRA-RISK Tunisia

**Satellite-based infrastructure screening for Greater Tunis. Screening and prioritization, not failure prediction.**

It answers "where should inspection teams look first?". It does not estimate collapse probability and must not be used to declare an asset safe or unsafe.

## What it does
- Finds Sentinel-1 scenes (`asf_search`) and submits interferogram jobs to ASF HyP3.
- Stacks the unwrapped interferograms into a line-of-sight (LOS) velocity map (`src/stacking.py`).
- Pulls bridges, primary/secondary/trunk roads, hospitals, schools and the port from OpenStreetMap and matches them to radar pixels.
- Flags anomalies with a robust z-score and an Isolation Forest (flag only when both agree), relative to the surrounding 1.5 km.
- Outputs a ranked GeoJSON layer, an interactive map, a CSV and a `POST /screen` API for SmartSDG.

## Current results (real Sentinel-1 data, preliminary)
- Window: 2024-07-09 to 2025-06-04, 21 interferogram pairs, ascending orbit.
- 30,254 velocity points; 2,231 assets found; **712 ranked** (at least 3 radar pixels); 1,519 reported as insufficient data (never "safe").
- 37 high priority, 2 medium, 673 low.

## Run it (Windows PowerShell)
```powershell
git clone https://github.com/nour-mahroug/INFRA-RISK.git
cd INFRA-RISK
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m pytest -q
python -m src.real_pipeline        # writes outputs/real/
uvicorn src.api:app --reload       # API on http://127.0.0.1:8000/docs
```
Open `outputs/real/map.html` in a browser. The committed `data/processed/velocity_real.tif` is enough: no Earthdata account is needed to run the pipeline or the API. An Earthdata login is only needed to download new HyP3 data. Secrets go in `.env` (copy `.env.example`), never in git. The API needs internet (OpenStreetMap).

## Outputs
- `outputs/real/alerts.geojson`, `outputs/real/map.html`, `outputs/real/ranked_assets.csv`

## Risk score
`risk_score = 100 × (0.35 V + 0.30 A + 0.20 I + 0.15 Q)`, each term in [0, 1]:
V = neighbourhood-relative velocity (normalized), A = anomaly intensity, I = asset importance (bridge/port 1.0, hospital/school 0.9, trunk/primary road 0.8, secondary 0.6), Q = data quality (coherence). Weights are in `config.yaml` and are a judgment call.

**Rank is tiered:** high priority first, then medium, then low, and by risk score inside each tier. That is why a high-priority asset can have a lower score than a medium one ranked after it.

## GeoJSON schema
Required properties on every feature: `asset_id`, `name`, `type`, `velocity_mm_yr`, `risk_score`, `rank`, `obs_start`, `obs_end`, `source`.
Optional: `priority`, `sample_count`, `velocity_rel_mm_yr`.
Units: LOS velocity in mm/yr, **positive = toward the satellite**. `metadata` includes `assets_found`, `assets_ranked`, `assets_insufficient_data` and a coverage note.

## API
`POST /screen` with `{"area": [west, south, east, north], "start_date": "2024-07-09", "end_date": "2025-06-04"}` returns the GeoJSON above. `GET /health` and `/docs` are also available.
- 422: invalid bbox, bbox outside Tunisia, bbox too large, dates reversed, period outside the observed window, or no radar coverage / no ranked asset.
- 503: radar raster missing or OpenStreetMap unavailable.

## Limits
- Sensitivity (`outputs/real/sensitivity.csv`): the ranking over all 712 assets is stable (Spearman 0.79 to 1.00), but the exact top 20 depends on the matching buffer, the neighbourhood radius and the Isolation Forest contamination (11 to 20 of the top 20 stay the same), and the number flagged ranges from 21 to 45 (37 in the baseline). Treat the top of the list as a shortlist to inspect, not an exact order.
- Preliminary: 11 months, so seasonal effects (groundwater, soil moisture, atmosphere) can look like movement.
- LOS only, not vertical.
- Re-referencing to the area median assumes most of Greater Tunis is stable; pixels with |v| above 50 mm/yr are masked as likely unwrapping errors.
- Pixels about 80 m apart: attribution to a single bridge or building is indicative.
- Only 712 of 2,231 assets can be assessed; short bridges and vegetated areas often lack coherent pixels.
- Not validated against ground truth yet. Clusters are "anomalous relative movement, cause to be confirmed by inspection".
- Not failure prediction. A low score does not certify safety.

See `docs/` for integration, limits, validation and the pitch. `src/pipeline.py` is the older synthetic-data demo path and is not used for the results above.

OpenStreetMap data © OpenStreetMap contributors (ODbL). Respect ASF/HyP3 terms for downloaded products.