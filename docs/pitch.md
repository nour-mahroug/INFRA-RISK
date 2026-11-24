# INFRA-RISK Tunisia — 3–5 minute pitch

## Slide 1 — The problem (35–45 sec)
Our cities depend on bridges, roads, hospitals, schools and ports. Ground settlement and slow deformation can develop over months or years, while visual inspections are periodic, costly and often reactive. The practical question for an inspection authority is not “can we predict collapse?” It is “where should we inspect first?”

## Slide 2 — The solution (40–50 sec)
INFRA-RISK Tunisia is a satellite-based pre-diagnostic screening module for Greater Tunis. Sentinel-1 radar observations can be processed as an InSAR time series to estimate slow line-of-sight movement. We associate those measurements with named infrastructure from OpenStreetMap and produce a transparent priority ranking. This is screening and prioritization, not failure prediction or structural diagnosis.

## Slide 3 — How it works (45–55 sec)
The production pipeline searches Sentinel-1 SLC scenes through ASF, submits short-baseline interferogram jobs to ASF HyP3, and uses MintPy's HyP3 processor workflow for SBAS time-series inversion. We sample reliable velocity pixels, associate them to nearby assets, and use two independent anomaly methods: robust Z-score and Isolation Forest. An anomaly flag is emitted only when both agree. A weighted score combines motion, anomaly intensity, asset importance and data quality.

## Slide 4 — Demo (45–60 sec)
Show the Folium map. Explain the red/orange/green priority colors and click a marker to reveal asset type, LOS velocity, score, rank and observation window. Open the GeoJSON and show the required SmartSDG properties. Call `POST /screen` in Swagger at `/docs`. **State clearly:** this hackathon demo uses a seeded synthetic field and labelled demo assets; it proves the software workflow, not measured deformation in Tunis.

## Slide 5 — SDG alignment and SmartSDG integration (35–45 sec)
The project supports SDG 9.1 through more resilient infrastructure planning, SDG 11.5 through improved awareness of urban exposure, and SDG 13 through attention to climate-related ground instability and coastal pressures. SmartSDG integration is intentionally simple: area and dates in, prioritized GeoJSON out. The platform can display the layer alongside its environmental and territorial indicators.

## Slide 6 — Limits (30–40 sec)
InSAR is line-of-sight only. Atmospheric noise and decorrelation can affect measurements, particularly over vegetation. Matching a pixel to an OSM asset is indicative, not proof of structural movement. A high score is not a failure probability; a low score does not certify safety. Engineering inspections remain essential.

## Slide 7 — The ask (20–30 sec)
We ask SmartSDG Tunisia and infrastructure stakeholders to support a pilot with validated Sentinel-1/HyP3 processing, an agreed stable reference area, and independent inspection records. The next step is to validate the screening layer against known stable and deforming sites, then integrate it as a repeatable inspection-prioritization service.
