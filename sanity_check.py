import numpy as np, pandas as pd, rasterio

with rasterio.open("data/processed/velocity_real.tif") as src:
    print(src.tags())
    v = src.read(1, masked=True).compressed()
print("pixels:", v.size)
print("min / p5 / median / p95 / max:", np.percentile(v, [0, 5, 50, 95, 100]).round(1))
print("share with |v| > 15 mm/yr:", round(float((abs(v) > 15).mean()), 3))

df = pd.read_csv("outputs/real/ranked_assets.csv")
print(df.shape)
if "priority" in df:
    print(df["priority"].value_counts())
cols = [c for c in ["rank", "name", "type", "velocity_mean", "velocity_rel",
                    "risk_score", "sample_count"] if c in df.columns]
print(df.sort_values("rank").head(20)[cols].to_string())