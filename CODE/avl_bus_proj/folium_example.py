# app_satellite_streetview_ridersize.py
import streamlit as st
import geopandas as gpd
import pandas as pd
import numpy as np
import folium
from streamlit_folium import st_folium
import html

URL = "https://gis.ashevillenc.gov/server/rest/services/Transportation/ARTBusStops/MapServer/10/query?outFields=*&where=1%3D1&f=geojson"
SIZE_COL = "rider_total"   # <- size by this column
SCALE = "log"              # "log" (good for skewed counts) or "linear"
MIN_R, MAX_R = 1,10       # min/max circle radius in pixels
CLIP_PCT = 2               # winsorize tails by % at each side (e.g., 2% -> clip 2nd–98th pct)

@st.cache_data(ttl=3600)
def load_data():
    gdf = gpd.read_file(URL)
    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=4326)
    else:
        gdf = gdf.to_crs(4326)

    gdf["lon"] = gdf.geometry.x
    gdf["lat"] = gdf.geometry.y
    gdf["streetview_url"] = gdf.apply(
        lambda r: f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={r['lat']:.6f},{r['lon']:.6f}",
        axis=1
    )
    return gdf

def compute_radius_from_series(series, scale="log", min_r=3, max_r=16, clip_pct=2):
    s = pd.to_numeric(series, errors="coerce")
    # Fill missing with median to avoid zero bubbles for NaNs
    s = s.fillna(s.median() if not np.isnan(s.median()) else 0)

    # Clip outliers (winsorize)
    if clip_pct and 0 < clip_pct < 50:
        lo = s.quantile(clip_pct/100.0)
        hi = s.quantile(1 - clip_pct/100.0)
        s = s.clip(lo, hi)

    # Normalize
    if scale == "log":
        shifted = s - s.min()
        norm = np.log1p(shifted)
        maxv = norm.max()
        norm = norm / maxv if maxv > 0 else np.zeros_like(norm)
    else:  # linear
        denom = (s.max() - s.min())
        norm = (s - s.min()) / denom if denom > 0 else np.full_like(s, 0.5, dtype=float)

    return (min_r + norm * (max_r - min_r)).astype(float)

st.title("ART Bus Stops — sized by rider_total (with Street View)")
gdf = load_data()
st.write(f"{len(gdf):,} stops loaded")

# Ensure column exists
if SIZE_COL not in gdf.columns:
    st.error(f"Column '{SIZE_COL}' not found in data. Available columns: {list(gdf.columns)}")
    st.stop()

# Compute per-point radius from rider_total
gdf["__radius"] = compute_radius_from_series(
    gdf[SIZE_COL], scale=SCALE, min_r=MIN_R, max_r=MAX_R, clip_pct=CLIP_PCT
)

# Map
center = [float(gdf["lat"].mean()), float(gdf["lon"].mean())]
m = folium.Map(location=center, zoom_start=12, tiles=None)
folium.TileLayer("Esri.WorldImagery", name="Esri Satellite").add_to(m)

candidate_cols = ["StopID","StopName","Routes","Direction","OnStreet","AtStreet"]
display_cols = [c for c in candidate_cols if c in gdf.columns]

for _, r in gdf.iterrows():
    # Tooltip (hover): includes rider_total + Street View URL text
    tooltip_lines = []
    for c in display_cols:
        tooltip_lines.append(f"<b>{html.escape(c)}</b>: {html.escape(str(r[c]))}")
    tooltip_lines.append(f"<b>{html.escape(SIZE_COL)}</b>: {html.escape(str(r[SIZE_COL]))}")
    tooltip_html = "<br>".join(tooltip_lines)

    # Popup (click): clickable Street View link
    popup_lines = []
    if "StopName" in gdf.columns:
        popup_lines.append(f"<b>{html.escape(str(r['StopName']))}</b>")
    for c in display_cols:
        if c != "StopName":
            popup_lines.append(f"<b>{html.escape(c)}</b>: {html.escape(str(r[c]))}")
    popup_lines.append(f"<b>{html.escape(SIZE_COL)}</b>: {html.escape(str(r[SIZE_COL]))}")
    popup_lines.append(f'<a href="{r["streetview_url"]}" target="_blank" rel="noopener">Open Google Street View</a>')
    popup_html = "<br>".join(popup_lines)

    folium.CircleMarker(
        location=[r["lat"], r["lon"]],
        radius=float(r["__radius"]),
        weight=0,
        color = 'blue',
        fill=True,
        fill_color = 'green',
        fill_opacity=0.9,
        tooltip=folium.Tooltip(tooltip_html, sticky=True),
        popup=folium.Popup(popup_html, max_width=350),
    ).add_to(m)

folium.LayerControl().add_to(m)
st_folium(m, height=600)
