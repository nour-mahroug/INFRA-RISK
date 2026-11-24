# SmartSDG Tunisia integration

## Role

INFRA-RISK is a loosely coupled screening plug-in. SmartSDG sends an area and observation window; INFRA-RISK returns a ranked GeoJSON FeatureCollection that the platform can render as a thematic layer or use to select assets for inspection.

## Inputs

`POST /screen` JSON body:

```json
{
  "area": [10.10, 36.74, 10.26, 36.86],
  "start_date": "2022-01-01",
  "end_date": "2025-06-30"
}
```

- `area`: exactly four WGS84 numbers `[west, south, east, north]`.
- `start_date`, `end_date`: ISO-8601 calendar dates; start must not exceed end.

## Outputs

GeoJSON `FeatureCollection`. Feature properties:

`asset_id`, `name`, `type`, `velocity_mm_yr`, `risk_score`, `rank`, `obs_start`, `obs_end`, `source`.

Example (illustrative demo response; not a real satellite measurement):

```json
{
  "type": "FeatureCollection",
  "features": [{
    "type": "Feature",
    "geometry": {"type": "Point", "coordinates": [10.21, 36.82]},
    "properties": {
      "asset_id": "demo-bridge-01",
      "name": "Pont de démonstration",
      "type": "bridge",
      "velocity_mm_yr": 4.8,
      "risk_score": 68.4,
      "rank": 1,
      "obs_start": "2022-01-01",
      "obs_end": "2025-06-30",
      "source": "SYNTHETIC_DEMO"
    }
  }],
  "metadata": {
    "project": "INFRA-RISK Tunisia",
    "positioning": "Screening and prioritization, not failure prediction"
  }
}
```

## Technical requirements

- REST/JSON over HTTP; OpenAPI documentation at `/docs`.
- GeoJSON geometries use EPSG:4326.
- Suggested deployment: containerized service behind SmartSDG's API gateway.
- The platform should retain `source` and metadata when ingesting the layer.
- Suggested refresh cadence: only after a new validated InSAR time series is available; avoid presenting synthetic demo refreshes as observations.
- Suggested consumer behavior: display ranked assets, expose observation window and source, and route high-priority candidates to qualified inspection teams.

## Local test

```bash
make run-pipeline
make run-api
curl -X POST http://localhost:8000/screen \
  -H 'Content-Type: application/json' \
  -d '{"area":[10.10,36.74,10.26,36.86],"start_date":"2022-01-01","end_date":"2025-06-30"}'
```

`GET /health` is a liveness endpoint. `/docs` is generated automatically by FastAPI.
