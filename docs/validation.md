# Validation and quality report

## Hackathon software validation

The deterministic demo path was executed end-to-end on the repository: raster generation, asset inventory, metric nearest-asset association, anomaly scoring, GeoJSON serialization, and Folium rendering. Automated tests cover robust-Z outlier response, score bounds and rank ordering, and required GeoJSON properties. Run `make test` and `make run-pipeline` to reproduce.

## What this does not validate

The demo velocity field is synthetic. Passing software tests does **not** establish that any location in Greater Tunis is subsiding or that an infrastructure asset is moving. No field survey or independently validated real Sentinel-1 time series is bundled with this hackathon artifact.

## Production validation protocol

1. Select and document a stable reference point/area; retain the reference coordinates and rationale with the run metadata.
2. Check HyP3 job completion, acquisition dates, orbit consistency, perpendicular baselines, and product coverage.
3. Apply coherence filtering and inspect the spatial distribution of valid pixels; mask vegetation/decorrelated areas where appropriate.
4. Compare nominally stable urban/rocky reference zones against approximately 0 mm/year, allowing for uncertainty and residual atmospheric noise.
5. Compare known deformation candidates (including published local subsidence/land-reclamation studies) with independent geotechnical or survey evidence.
6. Run sensitivity checks over robust-Z thresholds (for example 2.0, 2.5, 3.0 MAD), coherence thresholds, and asset buffer distances (30, 40, 50 m). Report rank stability and disagreements.
7. Have a qualified geotechnical/structural engineer review high-priority candidates before operational action.

## Acceptance status

- End-to-end demo workflow: software-validated.
- GeoJSON required fields and serialization: automated-test validated.
- Interactive map generation: smoke-tested by pipeline execution.
- API request/response contract: implemented with Pydantic validation; deployment smoke test should be run in the target environment.
- Scientific accuracy against real Greater Tunis deformation: **not yet validated**; requires production InSAR and independent reference data.
