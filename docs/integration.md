# SmartSDG Tunisia integration

## Role

INFRA-RISK is a loosely coupled screening plug-in. SmartSDG sends an area and an observation window; INFRA-RISK returns a ranked GeoJSON FeatureCollection that the platform can display as a thematic layer or use to choose assets for inspection. It is a prioritization aid, not a failure prediction or structural diagnosis.

## Input

`POST /screen`, JSON body:

```json
{
  "area": [10.10, 36.74, 10.34, 36.86],
  "start_date": "2024-07-09",
  "end_date": "2025-06-04"
}
```

- `area`: exactly four WGS84 numbers `[west, south, east, north]`, west < east, south < north, inside Tunisia (lon 7.5 to 11.7, lat 30.0 to 37.6), at most about 0.1 square degrees.
- `start_date`, `end_date`: ISO-8601 dates, start not after end. The period must overlap the observed radar window (currently 2024-07-09 to 2025-06-04); the result always describes that window.
- The area must be covered by the radar raster (Greater Tunis at present). Assets are fetched live from OpenStreetMap, so the service needs internet access.

## Output

GeoJSON `FeatureCollection` in EPSG:4326, sorted by `rank`.

Required properties on every feature: `asset_id`, `name`, `type`, `velocity_mm_yr`, `risk_score`, `rank`, `obs_start`, `obs_end`, `source`.
Optional properties: `priority` (`high`, `medium`, `low`), `sample_count` (radar pixels behind the asset), `velocity_rel_mm_yr` (velocity relative to the surrounding 1.5 km).

Units: line-of-sight (LOS) velocity in mm/yr, **positive = toward the satellite**. `risk_score` is 0 to 100.

**Rank is tiered:** high priority first, then medium, then low, and by score inside each tier.

Example (excerpt from the real output; geometry omitted):

```json
{
  "type": "FeatureCollection",
  "features": [{
    "type": "Feature",
    "geometry": "...",
    "properties": {
      "asset_id": "58bf347efe41",
      "name": "المعهد الثانوي 20 مارس",
      "type": "school",
      "velocity_mm_yr": -10.87,
      "risk_score": 85.4,
      "rank": 1,
      "obs_start": "2024-07-09",
      "obs_end": "2025-06-04",
      "source": "Sentinel-1 / HyP3 / stacking",
      "priority": "high",
      "sample_count": 4,
      "velocity_rel_mm_yr": -10.04
    }
  }],
  "metadata": {
    "project": "INFRA-RISK Tunisia",
    "positioning": "Screening and prioritization, not failure prediction",
    "source": "Sentinel-1 / HyP3 / stacking",
    "feature_count": 712,
    "assets_found": 2231,
    "assets_ranked": 712,
    "assets_insufficient_data": 1519,
    "min_samples": 3,
    "coverage_note": "712 of 2231 assets ranked; the rest had insufficient radar data (not 'safe').",
    "obs_start": "2024-07-09",
    "obs_end": "2025-06-04",
    "n_pairs": "21",
    "reference": "auto: most coherent 2% of pixels"
  }
}
```

Assets with too few radar pixels are **not** in the layer. `metadata` reports how many were left out. Absence from the layer means "not assessed", never "safe".

## Errors

| Status | Meaning |
|---|---|
| 422 | Invalid area (order, outside Tunisia, too large), dates reversed, period outside the observed window, no radar coverage in the area, or no asset with enough pixels. `detail` holds a readable message. |
| 503 | Radar raster missing, or OpenStreetMap (Overpass) unavailable. |
| 500 | Unexpected error; see the server log. |

`GET /health` returns `{"status": "ok", "raster_present": true, ...}`.

## Technical requirements

- REST/JSON over HTTP; OpenAPI documentation at `/docs`.
- Python service (FastAPI); containerized deployment behind SmartSDG's API gateway is suggested.
- The first call for an area queries OpenStreetMap and takes a few seconds; repeat calls for the same area are served from a cache.
- The platform should keep `source`, the observation window and `metadata` when ingesting the layer, and show the screening-only message to end users.
- Refresh only when a new processed Sentinel-1 time series is available.
- Suggested consumer behavior: display ranked assets, show `sample_count` and the observation window, and route high-priority assets to qualified inspection teams.

## Local test

```powershell
python -m src.real_pipeline
uvicorn src.api:app --reload
```

Then open `http://127.0.0.1:8000/docs`, or:

```powershell
curl -X POST http://127.0.0.1:8000/screen -H "Content-Type: application/json" -d "{\"area\":[10.10,36.74,10.34,36.86],\"start_date\":\"2024-07-09\",\"end_date\":\"2025-06-04\"}"
```