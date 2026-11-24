import zipfile
from pathlib import Path
import rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

W, S, E, N = 10.10, 36.74, 10.26, 36.86   # same bbox as config.yaml
for z in sorted(Path("data/raw").glob("*.zip")):
    try:
        with zipfile.ZipFile(z) as zf:
            member = [m for m in zf.namelist() if m.endswith("_corr.tif")][0]
        with rasterio.open(f"zip://{z.as_posix()}!{member}") as src:
            b = transform_bounds("EPSG:4326", src.crs, W, S, E, N)
            win = from_bounds(*b, transform=src.transform)
            a = src.read(1, window=win, boundless=True, fill_value=0)
            print(f"{(a > 0).mean() * 100:5.1f}% of the area has data   {z.name[:48]}")
    except Exception as exc:
        print("ERROR", z.name[:48], type(exc).__name__, exc)