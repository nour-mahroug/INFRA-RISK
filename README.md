# INFRA-RISK Tunisia

**Satellite-based infrastructure screening for Greater Tunis. Screening and prioritization — not failure prediction.**

INFRA-RISK is a pre-diagnostic decision-support module designed to help a municipality or infrastructure operator answer **“where should inspection teams look first?”** It is not a structural-health diagnosis, does not estimate collapse probability, and must not be used to declare an asset safe or unsafe.

> **Demo data warning:** the default hackathon run uses a deterministic synthetic LOS velocity field with planted hotspots. These values are simulated, not Sentinel-1 observations. The UI, GeoJSON `source`, and API metadata identify the demo mode.

## What it delivers

- Sentinel-1 SLC discovery with `asf_search`; cloud interferogram submission with ASF HyP3 (production path).
- MintPy `processor=hyp3` SBAS workflow adapter for HyP3 products.
- OSM infrastructure inventory (bridges, selected roads, hospitals, schools, port features).
- Spatial association of velocity samples to assets.
- Robust Z-score + Isolation Forest consensus; an anomaly flag is set only when both agree.
- Transparent 0–100 ranking, GeoJSON FeatureCollection, Folium map, ranked CSV and FastAPI `/screen`.

## Quick start (demo path)

Python 3.11 is recommended.

```bash
git clone <your-repository-url>
cd infra-risk-tunisia
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
make test
make run-pipeline
```

The pipeline writes:
- `outputs/alerts.geojson`
- `outputs/map.html`
- `outputs/ranked_assets.csv`
- `data/processed/demo_velocity.tif`

Open `outputs/map.html` in a browser. Demo mode does not require credentials or network access for the asset layer.

## API

```bash
make run-api
```

- Health: `GET http://localhost:8000/health`
- Screen: `POST http://localhost:8000/screen`
- Interactive OpenAPI docs: `http://localhost:8000/docs`

Example request:

```bash
curl -X POST http://localhost:8000/screen \
  -H "Content-Type: application/json" \
  -d '{"area":[10.10,36.74,10.26,36.86],"start_date":"2022-01-01","end_date":"2025-06-30"}'
```

The API lazily generates demo outputs if no alert file exists. The request area is `[west, south, east, north]` in WGS84.

## Architecture

```text
                  ┌─────────────────────────────┐
                  │ config.yaml / request bbox  │
                  └──────────────┬──────────────┘
                                 │
       PRODUCTION                ▼                 DEMO
┌──────────────────┐   ┌──────────────────┐   ┌─────────────────────┐
│ ASF Sentinel-1   │──▶│ HyP3 InSAR jobs  │   │ seeded synthetic    │
│ SLC discovery    │   │ cloud processing│   │ LOS velocity raster │
└──────────────────┘   └────────┬─────────┘   └──────────┬──────────┘
                                ▼                        │
                       ┌──────────────────┐              │
                       │ MintPy SBAS      │              │
                       │ velocity / LOS   │              │
                       └────────┬─────────┘              │
                                └───────────┬────────────┘
                                            ▼
                                ┌─────────────────────┐
                                │ OSM assets + spatial│
                                │ association         │
                                └──────────┬──────────┘
                                           ▼
                                ┌─────────────────────┐
                                │ robust Z +          │
                                │ Isolation Forest    │
                                └──────────┬──────────┘
                                           ▼
                                ┌─────────────────────┐
                                │ weighted risk rank  │
                                └──────┬────────┬─────┘
                                       ▼        ▼
                                  GeoJSON    Folium map
                                       │
                                       ▼
                                  FastAPI /screen
                                       │
                                       ▼
                                  SmartSDG Tunisia
```

## Risk scoring

For each asset, four normalized terms are combined:

`risk_score = 100 × (0.35 × V + 0.30 × A + 0.20 × I + 0.15 × Q)`

- `V`: absolute mean LOS velocity normalized to 15 mm/year and clipped to `[0,1]`.
- `A`: robust anomaly intensity (`robust_z / (2 × threshold)`, clipped to `[0,1]`).
- `I`: asset importance: bridge/port 1.0; hospital/school 0.9; trunk/primary road 0.8; secondary road 0.6.
- `Q`: mean coherence / data-quality proxy, clipped to `[0,1]`.

The weights are configurable in `config.yaml` and sum to 1.0. A binary anomaly flag is stricter than the continuous ranking: **robust Z-score ≥ 2.5 MAD and Isolation Forest outlier must both be true**. Ranking is an inspection-priority aid, not a failure probability.

## GeoJSON schema

Each Feature has a geometry in WGS84 and these properties:

| Field | Type | Meaning |
|---|---|---|
| `asset_id` | string | Stable asset identifier |
| `name` | string | OSM or demo asset name |
| `type` | string | bridge, road_primary, road_secondary, road_trunk, hospital, school, port |
| `velocity_mm_yr` | number | Mean LOS velocity, mm/year |
| `risk_score` | number | Weighted screening score, 0–100 |
| `rank` | integer | Priority rank, 1 = highest |
| `obs_start`, `obs_end` | date string | Observation window |
| `source` | string | `SYNTHETIC_DEMO` or `Sentinel-1 / HyP3 / MintPy` |

The collection also carries metadata describing the project and screening-only positioning.

## Production processing

Set environment variables in a local `.env` file (copy `.env.example`):

```dotenv
ASF_USERNAME=your_asf_username
ASF_PASSWORD=your_asf_password
HYP3_API_KEY=your_hyp3_api_key
```

Never commit `.env`. The production command is:

```bash
python -m src.pipeline --config config.yaml
```

The demo command is `python -m src.pipeline --config config.yaml --demo`. Production requires a valid ASF account, HyP3 quota/queue availability, downloaded HyP3 products, and a compatible MintPy environment. The MintPy adapter creates a minimal template and invokes `prep_hyp3.py` and `smallbaselineApp.py`; inspect product compatibility and reference-point selection before operational use. If production processing fails, the orchestrator logs the exception and explicitly switches to synthetic demo data so the hackathon demonstration can complete.

## Docker

```bash
cp .env.example .env
docker compose up --build
```

The compose service creates demo outputs and then starts the API on port 8000. To inspect the map, run the pipeline locally or mount/open `outputs/map.html`.

## Validation

`make test` checks robust outlier scoring, bounded scores/ranks, and required GeoJSON fields. The demo uses a fixed random seed for reproducibility. For a scientific validation report, compare results against independently documented stable reference zones and known subsidence studies; the synthetic demo itself is a software demonstration, not validation of real ground motion.

## Limitations and responsible use

- LOS-only displacement: a single viewing geometry does not recover full 3D movement.
- Atmospheric delay and residual orbital errors can mimic deformation; reference-point choice matters.
- Temporal/spatial decorrelation is significant over vegetation and changing surfaces.
- Asset attribution is indicative: satellite pixel footprints and OSM geometry do not prove that a structure itself is moving.
- Resolution and coherence limit which assets can be assessed.
- A high score means “consider inspection sooner,” not “this asset will fail.”
- A low score does not certify safety. Field inspection and engineering assessment remain necessary.

See [`docs/limits.md`](docs/limits.md), [`docs/integration.md`](docs/integration.md), [`docs/validation.md`](docs/validation.md), and [`docs/pitch.md`](docs/pitch.md).

## License and data attribution

OpenStreetMap data is © OpenStreetMap contributors and is available under the ODbL. Respect ASF/HyP3 terms, quotas, and attribution requirements for downloaded products. Choose and add a repository license before public release.
