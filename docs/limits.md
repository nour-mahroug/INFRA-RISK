# Assumed limitations and responsible interpretation

1. **LOS-only measurement.** Sentinel-1 InSAR measures displacement projected onto the satellite line of sight. A single orbit/direction cannot independently resolve vertical and horizontal components. Positive/negative sign depends on the processing convention.
2. **Atmospheric noise.** Water-vapor delay, residual orbit errors, and reference-point choice can introduce apparent motion. A stable reference point must be selected and documented for production.
3. **Decorrelation over vegetation.** Vegetated, agricultural, water, or rapidly changing surfaces may have low coherence. The pipeline should suppress or mark low-quality pixels rather than imply precision.
4. **Indicative asset attribution.** A pixel or buffer near an OSM feature is not proof that the bridge, road, hospital, or school itself is deforming. Resolution, geometry accuracy, and nearby ground movement affect attribution.
5. **Prioritization, not prediction.** Risk score is a screening index for ordering follow-up inspection. It is not a probability of failure, remaining useful life, diagnosis, or prediction of when a structure will collapse.
6. **Demo mode is synthetic.** The seeded velocity raster and demo asset inventory are generated for reproducible software demonstration. They must not be used for public safety decisions or represented as satellite observations.
7. **Algorithmic limitations.** Robust Z-score and Isolation Forest identify statistical outliers, not engineering damage. Consensus reduces single-model false positives but does not constitute ground truth.
8. **OSM completeness.** OpenStreetMap coverage and naming are uneven. Missing or misclassified assets may not appear in the output.

Operational use requires validated InSAR products, coherence screening, documented reference point, sensitivity analysis, independent comparison with known stable/deforming areas, and field inspection.
