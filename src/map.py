from __future__ import annotations
import html
import logging
from pathlib import Path
import geopandas as gpd
import folium

LOG = logging.getLogger(__name__)
RED, ORANGE, GREEN = "#d73027", "#fc8d32", "#1a9850"
TOP_N = 20


def _color(row, rank: int, total: int) -> str:
    """Red = consensus anomaly, orange = risk score >= 55, green = the rest (from score_assets)."""
    priority = row.get("priority")
    if priority is not None:
        return {"high": RED, "medium": ORANGE}.get(str(priority), GREEN)
    fraction = rank / max(total, 1)   # fallback when no priority column exists
    return RED if fraction <= .25 else (ORANGE if fraction <= .60 else GREEN)


def _fmt(value, digits: int = 1) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "n/a"


def _table_html(frame: gpd.GeoDataFrame) -> str:
    if "rank" not in frame.columns:
        return ""
    rows = []
    for _, r in frame.sort_values("rank").head(TOP_N).iterrows():
        rel = _fmt(r["velocity_rel"]) if "velocity_rel" in frame.columns else "n/a"
        rows.append(
            f"<tr><td>{int(r['rank'])}</td><td>{html.escape(str(r['name']))}</td>"
            f"<td>{html.escape(str(r['type']))}</td><td>{_fmt(r.get('velocity_mean'))}</td>"
            f"<td>{rel}</td><td>{_fmt(r.get('risk_score'))}</td></tr>")
    return (
        '<div style="position:fixed;top:70px;right:10px;z-index:9999;background:white;padding:8px;'
        'border:1px solid #aaa;border-radius:5px;font-size:11px;max-height:45vh;overflow:auto;max-width:430px">'
        f"<b>Top {TOP_N} assets to inspect first</b>"
        '<table style="border-collapse:collapse;margin-top:4px" cellpadding="2">'
        "<tr style='text-align:left;border-bottom:1px solid #999'><th>#</th><th>Asset</th><th>Type</th>"
        "<th>LOS mm/yr</th><th>vs. area</th><th>Score</th></tr>"
        + "".join(rows) + "</table>"
        '<div style="color:#555;margin-top:4px">LOS = along the satellite line of sight. '
        "vs. area = velocity minus the median of the surrounding 1.5 km.</div></div>")


def create_map(frame: gpd.GeoDataFrame, cfg: dict, output_path: str | Path | None = None) -> str:
    west, south, east, north = cfg["aoi"]["bbox"]
    center = [(south+north)/2, (west+east)/2]
    fmap = folium.Map(
        location=center,
        zoom_start=12,
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
        attr="Tiles © Esri",
    )
    total = len(frame)
    has_rel = "velocity_rel" in frame.columns
    # Draw the lowest-priority assets first so the red (high priority) markers end up on top.
    ordered = frame.sort_values("rank", ascending=False) if "rank" in frame.columns else frame
    for _, row in ordered.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        point = geom.representative_point()
        rank = int(row.get("rank", total))
        color = _color(row, rank, total)
        name = html.escape(str(row["name"]))
        popup = folium.Popup(
            f"<b>{name}</b><br>Type: {html.escape(str(row['type']))}<br>"
            f"LOS velocity: {row.get('velocity_mean', 0):.2f} mm/yr<br>"
            + (f"Relative to surroundings: {row['velocity_rel']:.2f} mm/yr<br>" if has_rel else "")
            + f"Risk score: {row.get('risk_score', 0):.1f}/100<br>"
            f"Rank: {rank}<br>Window: {cfg['dates']['start']} → {cfg['dates']['end']}<br>"
            f"Consensus anomaly: {bool(row.get('is_anomaly', False))}<br>"
            "Source: Sentinel-1 / ASF HyP3 / stacking (LOS)",
            max_width=320)
        folium.CircleMarker([point.y, point.x], radius=7, color=color, fill=True,
                            fill_opacity=.85, popup=popup,
                            tooltip=f"#{rank} {name}").add_to(fmap)
    legend = f"""<div style="position:fixed;bottom:25px;left:25px;z-index:9999;background:white;
    padding:10px;border:1px solid #aaa;border-radius:5px;font-size:12px">
    <b>INFRA-RISK priority</b><br>
    <span style="color:{RED}">●</span> High: both anomaly methods agree<br>
    <span style="color:{ORANGE}">●</span> Medium: risk score 55 or more<br>
    <span style="color:{GREEN}">●</span> Low priority
    </div>"""
    fmap.get_root().html.add_child(folium.Element(legend))
    fmap.get_root().html.add_child(folium.Element(_table_html(frame)))
    banner = "Screening only — not a structural diagnosis or failure prediction"
    fmap.get_root().html.add_child(folium.Element(
        f'<div style="position:fixed;top:10px;left:50px;z-index:9999;background:#fff;padding:8px;'
        f'border:1px solid #777;font-weight:bold">{banner}</div>'))
    path = Path(output_path or cfg["paths"]["map"])
    path.parent.mkdir(parents=True, exist_ok=True)
    fmap.save(str(path))
    LOG.info("Saved interactive map to %s", path)
    return str(path)