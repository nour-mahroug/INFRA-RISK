# INFRA-RISK Tunisia — 3–5 minute pitch

## Slide 1 — The problem (35 sec)
Bridges, roads, hospitals and schools in Greater Tunis are inspected on a schedule, not by need. Slow ground movement can build up for months before anyone sees it. The practical question is not "when will it fail?" but "where should we inspect first?"

## Slide 2 — The solution (40 sec)
INFRA-RISK Tunisia is a satellite-based screening and prioritization tool. It measures slow ground movement from free Sentinel-1 radar (InSAR), matches it to OpenStreetMap infrastructure, flags anomalies and ranks assets. It is not failure prediction and not a structural diagnosis.

## Slide 3 — How it works (50 sec)
1. Sentinel-1 scenes are found with asf_search and processed into interferograms by ASF HyP3 (21 pairs, July 2024 to June 2025).
2. We stack the unwrapped interferograms into a line-of-sight velocity map (statistics, not AI).
3. Assets from OpenStreetMap are matched to nearby radar pixels. An asset is ranked only if it has at least 3 pixels.
4. Two checks flag anomalies relative to the surrounding 1.5 km: a robust z-score and an unsupervised Isolation Forest. High priority only when both agree.
5. A transparent weighted score ranks assets: movement, anomaly, importance, data quality.

Result: 30,254 radar points, 2,231 assets found, 712 ranked, 37 high priority.

## Slide 4 — Live demo (60 sec)
Open the map: red, orange and green priorities, the top-20 table, a popup (type, LOS velocity, score, rank, window). Open Swagger at /docs and run POST /screen on Greater Tunis: GeoJSON out. Then send a bbox outside Tunisia: a clean 422, not a crash.
Say: "This is real Sentinel-1 data, with preliminary results."

## Slide 5 — SDGs and SmartSDG integration (40 sec)
SDG 9.1 (resilient infrastructure, evidence-based maintenance) and SDG 11.5 (reduce disaster losses), with SDG 13 as a secondary link. Integration is simple: area and dates in, ranked GeoJSON out, ready to display as a layer on SmartSDG.

## Slide 6 — Limits, stated openly (40 sec)
- Preliminary: only 11 months of data, so seasonal effects can look like movement.
- Line-of-sight only, not vertical.
- Pixels are about 80 m apart: matching a pixel to one bridge is indicative.
- Only 712 of 2,231 assets are assessed. The rest are "insufficient data", never "safe".
- Some clusters (including positive velocities in the southeast) may be atmospheric or orbit effects. We call them anomalous relative movement, cause to be confirmed by inspection.
- A high score means inspect sooner, not "it will fail".

## Slide 7 — The ask (25 sec)
A pilot with SmartSDG and infrastructure owners: a longer time series, comparison against known sites and inspection records, and a repeatable prioritization service.

One-liner: "Physics-based InSAR measures movement, robust statistics and an unsupervised check flag it, and a transparent score ranks assets. We rank only assets with enough radar pixels and report the rest as insufficient data, not as safe."