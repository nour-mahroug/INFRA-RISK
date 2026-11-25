# Validation and quality report

## What was verified (software and reproducibility)

- 25 automated tests pass (`python -m pytest -q`): anomaly scoring, alert schema, stacking, API behaviour (good bbox, invalid bbox, bbox outside Tunisia, bbox too large, reversed dates, period outside the window, no coverage, OpenStreetMap unavailable, raster missing) and the required fields on every feature of the real alert layer.
- The real pipeline (`python -m src.real_pipeline`) reruns from the committed raster and reproduces the same counts: 30,254 velocity points, 2,231 assets found, 712 ranked, 37 high priority.
- Every feature in `outputs/real/alerts.geojson` carries the nine required properties; ranks and asset ids are unique; scores are within 0 to 100.
- The raster is tagged as Sentinel-1 data and the code refuses to label an untagged raster as real.
- After re-referencing, the mean velocity over the ranked assets is about 0 mm/yr (-0.06), as expected from the area-median assumption. This checks the processing, not the physics.

## Sensitivity analysis (`outputs/real/sensitivity.csv`)

Baseline: buffer 60 m, at least 3 pixels, z threshold 2.5, contamination 0.10, neighbourhood 1.5 km (712 assets, 37 flagged).

| Variant | Assets | Flagged | Top-20 overlap | Spearman |
|---|---|---|---|---|
| buffer 80 m | 849 | 42 | 14 | 0.99 |
| buffer 100 m | 940 | 45 | 11 | 0.98 |
| min coherence 0.45 / 0.55 | 712 | 37 | 20 / 20 | 1.00 |
| neighbourhood radius 1000 m | 712 | 34 | 18 | 0.86 |
| neighbourhood radius 2500 m | 712 | 25 | 11 | 0.79 |
| robust z threshold 2.0 | 712 | 45 | 18 | 1.00 |
| robust z threshold 3.0 | 712 | 22 | 18 | 1.00 |
| isolation contamination 0.05 | 712 | 21 | 12 | 1.00 |
| isolation contamination 0.15 | 712 | 38 | 20 | 1.00 |

Reading: the overall ranking is stable, but the exact top 20 and the number of flagged assets depend on the buffer, the neighbourhood radius and the contamination. The coherence threshold has no effect because the raster already contains only coherent pixels. The top of the list is therefore a shortlist to inspect, not an exact order.

## What is NOT validated

- There is no comparison with ground truth: no levelling or GNSS survey, no inspection records, no independent processing of the same data.
- The 11-month window is too short to separate seasonal effects from trends.
- The spatial pattern has not been verified. Negative velocities (about -8 to -12 mm/yr) cluster in the west and northwest (Sidi Hassine, Séjoumi, Zahrouni) and along the north shore of the Lake of Tunis, which is **consistent with** soft or reclaimed ground, but this is not confirmed. Positive velocities (about +8 to +12 mm/yr) cluster in the southeast (Mégrine, Radès, Ben Arous) and in parts of Ariana and Menzah; uplift of that size in an urban area is unusual and may be a residual atmospheric or orbit ramp. We call these "anomalous relative movement, cause to be confirmed by inspection".
- The 50 mm/yr outlier threshold and the score weights have not been tested against labelled data.

## Planned validation

1. Compare the negative cluster with published studies on the Lake of Tunis, Sebkhet Séjoumi and reclaimed-land settlement; report what matches and what does not.
2. Inspect the velocity map for a smooth regional ramp (atmosphere or orbit) and, if present, remove it and rerun.
3. Check coverage by asset type (`check_coverage.py`) and report which asset classes are rarely assessed.
4. Extend the time series beyond 11 months and compare seasonal and trend components.
5. Compare high-priority assets with independent evidence (inspection records, geotechnical or survey data), reviewed by a qualified engineer.

## Acceptance status

| Item | Status |
|---|---|
| Real pipeline reproducible from the committed raster | Verified |
| GeoJSON schema and API contract | Automated-test validated |
| Map generation | Verified by pipeline run |
| Sensitivity of ranking to parameters | Reported (above) |
| Scientific accuracy against real ground motion in Greater Tunis | **Not yet validated** |