"""
AquaVeritas Streamlit Dashboard
---------------------------------
Four tabs:
  Global Monitor  — world map + sustained-shrinkage alert panel
  Location Detail — per-location time series + latest observation card
  Model Evaluation — three-way accuracy comparison from comparison.json
  Live Prediction  — fetch Sentinel-2 imagery and run on-board inference

Run:
    streamlit run app/app.py
"""

import json
import os
import sys
import urllib.request
from html import escape as _html_escape
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pydeck as pdk
import streamlit as st
from dotenv import load_dotenv

# Load .env from project root (two levels up from app/)
_ENV_PATH = Path(__file__).parent.parent / ".env"
load_dotenv(_ENV_PATH)

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aquaveritas.db import Database
from aquaveritas.locations import LOCATIONS, LOCATIONS_BY_ID

REPORTS_DIR = Path(__file__).parent.parent / "data" / "reports"

# ── Mapbox token — st.secrets takes priority, .env as fallback ───────────────
_MAPBOX_TOKEN = (
    st.secrets.get("MAPBOX_TOKEN", "")
    or os.getenv("MAPBOX_TOKEN", "")
).strip()
if _MAPBOX_TOKEN:
    pdk.settings.mapbox_key = _MAPBOX_TOKEN
    os.environ["MAPBOX_API_KEY"] = _MAPBOX_TOKEN   # pydeck env-var fallback

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="AquaVeritas",
    page_icon=":satellite:",
    layout="wide",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Nunito+Sans:opsz,wght@6..12,400;6..12,500;6..12,600;6..12,700&family=Source+Code+Pro&display=swap');

html, body, [class*="css"], .stMarkdown, .stText, button, input, select {
    font-family: 'Nunito Sans', sans-serif !important;
}

/* ── Sidebar — Dark Navy ── */
[data-testid="stSidebar"] {
    background-color: #032D60 !important;
    border-right: 1px solid #021E42;
}
[data-testid="stSidebar"] * { color: #FFFFFF !important; }
[data-testid="stSidebar"] .stSelectbox > label,
[data-testid="stSidebar"] p { color: rgba(255,255,255,0.72) !important; }
[data-testid="stSidebar"] [data-baseweb="select"] > div {
    background: rgba(255,255,255,0.10) !important;
    border-color: rgba(255,255,255,0.25) !important;
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    gap: 0;
    border-bottom: 2px solid #D8DDE6;
}
.stTabs [data-baseweb="tab"] {
    font-weight: 600;
    font-size: 0.875rem;
    color: #706E6B;
    padding: 0.625rem 1.25rem;
    border-bottom: 2px solid transparent;
    margin-bottom: -2px;
    background: transparent !important;
}
.stTabs [aria-selected="true"] {
    color: #00A1E0 !important;
    border-bottom-color: #00A1E0 !important;
}

/* ── Buttons ── */
.stButton > button {
    font-family: 'Nunito Sans', sans-serif !important;
    font-weight: 600;
    background-color: #00A1E0 !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 4px !important;
    letter-spacing: 0.02em;
    transition: background-color 0.15s ease;
}
.stButton > button:hover { background-color: #0088C7 !important; }
.stButton > button:disabled { background-color: #D8DDE6 !important; color: #706E6B !important; }

/* ── Metrics ── */
[data-testid="metric-container"] label {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: #706E6B !important;
    font-weight: 600;
}
[data-testid="stMetricValue"] { color: #032D60 !important; font-weight: 700 !important; }

/* ── Headings ── */
h1, h2, h3, h4 {
    font-family: 'Nunito Sans', sans-serif !important;
    color: #032D60 !important;
    font-weight: 700 !important;
}

/* ── Info / warning / error banners ── */
[data-testid="stAlert"] { border-radius: 4px; font-size: 0.875rem; }

/* ── Dataframe header ── */
[data-testid="stDataFrame"] th {
    background: #F4F6F9 !important;
    color: #032D60 !important;
    font-weight: 700 !important;
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}

/* ── Selectbox / inputs ── */
[data-baseweb="select"] > div, [data-baseweb="input"] > div {
    border-color: #D8DDE6 !important;
    border-radius: 4px !important;
}
[data-baseweb="select"] > div:focus-within,
[data-baseweb="input"] > div:focus-within {
    border-color: #00A1E0 !important;
    box-shadow: 0 0 0 2px rgba(0,161,224,0.2) !important;
}
</style>
""", unsafe_allow_html=True)

# ── Design tokens — Cloud Tower design system ─────────────────────────────────

CLR_SURFACE   = "#FFFFFF"
CLR_BORDER    = "#D8DDE6"
CLR_TEXT_PRI  = "#032D60"
CLR_TEXT_SEC  = "#706E6B"

CLR_RED    = "#C23934"
CLR_AMBER  = "#FF9A3C"
CLR_YELLOW = "#F5C518"
CLR_GREEN  = "#04844B"
CLR_GREY   = "#706E6B"
CLR_BLUE   = "#00A1E0"
CLR_TEAL   = "#00A1E0"
CLR_ORACLE = "#032D60"

# ── Constants ─────────────────────────────────────────────────────────────────

WATER_STATUS_COLOUR = {
    "shrinking":  [220, 50,  50,  200],
    "stable":     [250, 200, 50,  200],
    "flooded":    [30,  100, 200, 200],
    "recovering": [50,  180, 80,  200],
    "dry":        [160, 160, 160, 200],
    "unknown":    [100, 100, 100, 180],
}

STRESS_NUMERIC = {"none": 0, "low": 1, "moderate": 2, "severe": 3}

CORE_FIELDS = [
    "water_extent_status",
    "flood_risk",
    "water_clarity",
    "shoreline_encroachment",
]
BUFFER_FIELDS = [
    "agriculture_present",
    "crop_stress_level",
    "crop_stress_type",
    "cultivation_expanding_toward_water",
    "settlement_visible",
    "bare_soil_expansion",
]
FIELD_LABELS = {
    "water_extent_status":                "Water Extent Status",
    "flood_risk":                         "Flood Risk",
    "water_clarity":                      "Water Clarity",
    "shoreline_encroachment":             "Shoreline Encroachment",
    "agriculture_present":                "Agriculture Present",
    "crop_stress_level":                  "Crop Stress Level",
    "crop_stress_type":                   "Crop Stress Type",
    "cultivation_expanding_toward_water": "Cultivation Expanding",
    "settlement_visible":                 "Settlement Visible",
    "bare_soil_expansion":                "Bare Soil Expansion",
}

MAP_STYLE_DARK      = "mapbox://styles/mapbox/dark-v11"
MAP_STYLE_SATELLITE = "mapbox://styles/mapbox/satellite-streets-v12"
MAP_STYLE_FALLBACK  = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
MAP_STYLE = MAP_STYLE_SATELLITE if _MAPBOX_TOKEN else MAP_STYLE_FALLBACK

# ── Helpers ───────────────────────────────────────────────────────────────────

def _max_consecutive(values: list, target: str) -> int:
    max_run = current = 0
    for v in values:
        if str(v).lower() == target:
            current += 1
            max_run = max(max_run, current)
        else:
            current = 0
    return max_run


def _sustained_shrinkage(df: pd.DataFrame, threshold: int = 3) -> list[tuple]:
    results = []
    for loc_id in df["location_id"].unique():
        sub = (
            df[df["location_id"] == loc_id]
            .sort_values("observed_at")["water_extent_status"]
            .tolist()
        )
        run = _max_consecutive(sub, "shrinking")
        if run >= threshold:
            results.append((loc_id, run))
    return sorted(results, key=lambda x: -x[1])


def _check_llama(url: str) -> bool:
    try:
        urllib.request.urlopen(f"{url}/health", timeout=3)
        return True
    except Exception:
        return False


def _colour_for(field: str, value) -> str:
    if value is None:
        return "#555555"
    v = str(value).lower()
    if field == "water_extent_status":
        return {
            "shrinking": CLR_RED, "stable": CLR_YELLOW,
            "flooded": CLR_BLUE, "recovering": CLR_GREEN, "dry": CLR_GREY,
        }.get(v, "#777")
    if field == "flood_risk":
        return {"active": CLR_RED, "elevated": CLR_AMBER, "none": CLR_GREEN}.get(v, "#777")
    if field == "water_clarity":
        return {"poor": CLR_RED, "moderate": CLR_AMBER, "good": CLR_GREEN}.get(v, "#777")
    if field == "crop_stress_level":
        return {
            "severe": CLR_RED, "moderate": CLR_AMBER,
            "low": CLR_YELLOW, "none": CLR_GREEN,
        }.get(v, "#777")
    if field in (
        "shoreline_encroachment", "agriculture_present",
        "cultivation_expanding_toward_water", "settlement_visible", "bare_soil_expansion",
    ):
        if isinstance(value, bool):
            return CLR_RED if value else CLR_GREEN
        return CLR_RED if v in ("true", "yes", "1") else CLR_GREEN
    return CLR_TEAL


def _badge(field: str, label: str, value) -> str:
    """Render a coloured status badge. Model/user-derived values are HTML-escaped."""
    colour  = _colour_for(field, value)
    display = "—" if value is None else _html_escape(str(value))
    return (
        f'<div style="display:flex;align-items:center;gap:10px;'
        f'background:{CLR_SURFACE};border:1px solid {CLR_BORDER};'
        f'padding:8px 12px;border-radius:8px;margin-bottom:8px;">'
        f'<span style="width:8px;height:8px;border-radius:50%;'
        f'background:{colour};flex-shrink:0;"></span>'
        f'<span style="flex:1;">'
        f'<span style="display:block;color:{CLR_TEXT_SEC};font-size:0.72em;'
        f'text-transform:uppercase;letter-spacing:0.06em;line-height:1.4;">{label}</span>'
        f'<span style="color:{CLR_TEXT_PRI};font-size:0.97em;font-weight:500;">{display}</span>'
        f'</span>'
        f'</div>'
    )


def _unavailable_tile(label: str) -> str:
    return (
        f'<div style="background:{CLR_SURFACE};border:1px solid {CLR_BORDER};'
        f'border-radius:8px;padding:24px 12px;text-align:center;'
        f'color:{CLR_TEXT_SEC};font-size:0.8em;line-height:1.6;">'
        f'{_html_escape(label)}<br>No tile available</div>'
    )


def _mapbox_satellite_url(lon: float, lat: float, zoom: int = 10) -> str:
    return (
        f"https://api.mapbox.com/styles/v1/mapbox/satellite-v9/static/"
        f"{lon},{lat},{zoom}/600x340@2x"
        f"?access_token={_MAPBOX_TOKEN}"
    )


# ── Data loaders ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def load_all_observations() -> list[dict]:
    try:
        return Database().get_observations_for_dashboard()
    except Exception as exc:
        st.error(f"Database error: {exc}")
        return []


@st.cache_data(ttl=60)
def load_latest() -> list[dict]:
    try:
        rows = Database().get_latest_per_location()
        for r in rows:
            if "name" in r and "location_name" not in r:
                r["location_name"] = r["name"]
        return rows
    except Exception:
        return []


@st.cache_data(ttl=300)
def load_eval_metrics() -> dict | None:
    path = REPORTS_DIR / "comparison.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def to_df(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if "observed_at" in df.columns:
        df["observed_at"] = pd.to_datetime(df["observed_at"], utc=True)
    return df


# ── Load data ─────────────────────────────────────────────────────────────────

all_rows  = load_all_observations()
latest    = load_latest()
all_df    = to_df(all_rows)
latest_df = to_df(latest)
eval_data = load_eval_metrics()
has_data  = not all_df.empty

location_names = {loc.id: loc.name for loc in LOCATIONS}

# ── Header ────────────────────────────────────────────────────────────────────

st.title("AquaVeritas")
st.caption("On-board satellite freshwater monitoring — Liquid AI × DPhi Space Hackathon")
st.markdown(
    f'<p style="color:{CLR_TEXT_SEC};font-size:0.82em;margin:-4px 0 12px;">'
    "Global Monitor &nbsp;→&nbsp; Location Detail &nbsp;→&nbsp; "
    "Model Evaluation &nbsp;→&nbsp; Live Prediction"
    "</p>",
    unsafe_allow_html=True,
)

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Controls")
    # Single source of truth — all tabs read from st.session_state["selected_id"]
    _ALL = "__all__"
    selected_id = st.selectbox(
        "Water body",
        options=[_ALL] + list(location_names.keys()),
        format_func=lambda x: "— All sites —" if x == _ALL else location_names[x],
        key="selected_id",
    )
    selected_loc = LOCATIONS_BY_ID.get(selected_id) if selected_id != _ALL else None
    if selected_loc:
        st.caption(f"{selected_loc.lat:.3f}°N, {selected_loc.lon:.3f}°E")
    st.caption("Location selector controls all tabs")
    st.divider()
    st.metric("Total observations",  len(all_df) if has_data else 0)
    st.metric("Locations monitored", len(LOCATIONS))
    if eval_data:
        ft = eval_data.get("finetuned", {}).get("metrics", {})
        st.metric("Fine-tuned accuracy", f"{ft.get('overall', 0):.1%}")
    st.divider()
    if st.button("Refresh data"):
        st.cache_data.clear()
        st.rerun()

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_monitor, tab_location, tab_eval, tab_live = st.tabs(
    ["Global Monitor", "Location Detail", "Model Evaluation", "Live Prediction"]
)

# ═════════════════════════════════════════════════════════════════════════════
# TAB 1 — Global Monitor
# ═════════════════════════════════════════════════════════════════════════════

with tab_monitor:
    col_map, col_legend = st.columns([3, 1])

    with col_map:
        st.subheader("Global Water Body Status")

        # View: global overview unless a specific site is selected
        view = pdk.ViewState(
            latitude=selected_loc.lat if selected_loc else 10,
            longitude=selected_loc.lon if selected_loc else 25,
            zoom=5 if selected_loc else 1.8,
            pitch=25,
            bearing=0,
            transition_duration=800,
        )

        # Build map data from ALL 20 locations, merging in latest observations where available
        all_locs_df = pd.DataFrame([
            {"location_id": l.id, "name": l.name, "lat": l.lat, "lon": l.lon}
            for l in LOCATIONS
        ])
        if not latest_df.empty:
            loc_col = "location_name" if "location_name" in latest_df.columns else "name"
            obs_slim = latest_df[["location_id", "water_extent_status", "flood_risk", "crop_stress_level"]].copy()
            map_data = all_locs_df.merge(obs_slim, on="location_id", how="left")
        else:
            map_data = all_locs_df.copy()
            map_data["water_extent_status"] = None
            map_data["flood_risk"]          = None
            map_data["crop_stress_level"]   = None

        map_data["color"] = map_data["water_extent_status"].map(
            lambda s: WATER_STATUS_COLOUR.get(str(s).lower(), WATER_STATUS_COLOUR["unknown"])
            if pd.notna(s) else WATER_STATUS_COLOUR["unknown"]
        )
        map_data["color_halo"] = map_data["color"].map(
            lambda c: [c[0] // 3, c[1] // 3, c[2] // 3, 50]
        )
        map_data["tooltip_text"] = (
            map_data["name"]
            + map_data["water_extent_status"].apply(
                lambda s: f"\nStatus: {s}" if pd.notna(s) else "\nNo data yet"
            )
            + map_data["flood_risk"].apply(
                lambda s: f"\nFlood risk: {s}" if pd.notna(s) else ""
            )
            + map_data["crop_stress_level"].apply(
                lambda s: f"\nCrop stress: {s}" if pd.notna(s) else ""
            )
        )

        layer_halo = pdk.Layer(
            "ScatterplotLayer",
            data=map_data,
            get_position=["lon", "lat"],
            get_fill_color="color_halo",
            get_radius=18_000,
            radius_min_pixels=10,
            pickable=False,
            stroked=False,
        )
        layer_dots = pdk.Layer(
            "ScatterplotLayer",
            data=map_data,
            get_position=["lon", "lat"],
            get_fill_color="color",
            get_radius=8_000,
            radius_min_pixels=5,
            pickable=True,
            stroked=True,
            get_line_color=[255, 255, 255, 200],
            line_width_min_pixels=1,
        )
        layer_text = pdk.Layer(
            "TextLayer",
            data=map_data,
            get_position=["lon", "lat"],
            get_text="name",
            get_size=12,
            get_color=[255, 255, 255, 200],
            get_anchor="'middle'",
            get_alignment_baseline="'top'",
            get_pixel_offset=[0, 10],
            billboard=True,
        )
        layers  = [layer_halo, layer_dots, layer_text]
        tooltip = {"text": "{tooltip_text}"}

        if not has_data:
            st.info("No observations yet — run `scripts/predict.py` to populate the map.")

        st.pydeck_chart(
            pdk.Deck(
                layers=layers,
                initial_view_state=view,
                tooltip=tooltip,
                map_style=MAP_STYLE,
            ),
            use_container_width=True,
            height=520,
        )

    with col_legend:
        st.subheader("Legend")
        for status, colour in WATER_STATUS_COLOUR.items():
            if status == "unknown":
                continue
            r, g, b, _ = colour
            st.markdown(
                f'<span style="color:rgb({r},{g},{b})">&#9679;</span> {status.capitalize()}',
                unsafe_allow_html=True,
            )

    # ── Sustained shrinkage — full-width below map ────────────────────────────
    if has_data:
        shrink_locs = _sustained_shrinkage(all_df)
        if shrink_locs:
            st.markdown(
                f'<p style="color:{CLR_RED};font-size:0.78em;text-transform:uppercase;'
                f'letter-spacing:0.08em;margin:16px 0 8px;font-weight:600;">Sustained shrinkage</p>',
                unsafe_allow_html=True,
            )
            n_cols = min(len(shrink_locs), 5)
            alert_cols = st.columns(n_cols)
            for i, (loc_id, count) in enumerate(shrink_locs[:5]):
                name = location_names.get(loc_id, loc_id)
                with alert_cols[i]:
                    st.markdown(
                        f'<div style="background:{CLR_RED}18;border:1px solid {CLR_RED}55;'
                        f'border-radius:8px;padding:10px 14px;">'
                        f'<span style="color:{CLR_RED};font-size:0.7em;text-transform:uppercase;'
                        f'letter-spacing:0.06em;">{count} consecutive</span><br>'
                        f'<span style="color:{CLR_TEXT_PRI};font-weight:500;font-size:0.9em;">'
                        f'{_html_escape(name)}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

# ═════════════════════════════════════════════════════════════════════════════
# TAB 2 — Location Detail
# ═════════════════════════════════════════════════════════════════════════════

with tab_location:
    if not selected_loc:
        st.info("Select a water body from the sidebar to view location detail.")
        st.stop()

    st.subheader(location_names[selected_id])

    loc_df = (
        all_df[all_df["location_id"] == selected_id].copy()
        if has_data else pd.DataFrame()
    )

    if loc_df.empty:
        st.info(f"No observations yet for {location_names[selected_id]}.")
    else:
        col_water, col_crop = st.columns(2)

        with col_water:
            st.markdown("**Water body status over time**")
            fig = px.scatter(
                loc_df,
                x="observed_at",
                y="water_extent_status",
                color="flood_risk",
                color_discrete_map={
                    "none":     "#4CAF50",
                    "elevated": "#FF9800",
                    "active":   "#F44336",
                },
                category_orders={
                    "water_extent_status": ["flooded", "recovering", "stable", "shrinking", "dry"]
                },
                labels={"observed_at": "Date", "water_extent_status": "Status"},
                height=300,
            )
            fig.update_traces(marker_size=9)
            fig.update_layout(margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig, use_container_width=True)

        with col_crop:
            st.markdown("**Crop stress level over time**")
            loc_df["stress_num"] = loc_df["crop_stress_level"].map(STRESS_NUMERIC)
            fig2 = px.scatter(
                loc_df.dropna(subset=["stress_num"]),
                x="observed_at",
                y="stress_num",
                color="crop_stress_type",
                color_discrete_map={
                    "drought":      "#FF6B35",
                    "flood_damage": "#4FC3F7",
                    "none":         "#81C784",
                },
                labels={"observed_at": "Date", "stress_num": "Stress Level"},
                height=300,
            )
            fig2.update_yaxes(
                tickvals=[0, 1, 2, 3],
                ticktext=["None", "Low", "Moderate", "Severe"],
            )
            fig2.update_traces(marker_size=9)
            fig2.update_layout(margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig2, use_container_width=True)

        # ── Latest observation — badges match Tab 4 visual language ───────────
        st.markdown("**Latest observation**")
        latest_row = loc_df.sort_values("observed_at").iloc[-1]
        ts = latest_row.get("observed_at")
        st.caption(f"Observed {str(ts)[:10] if ts else '—'}")

        obs_core_col, obs_buf_col, obs_img_col = st.columns([2, 2, 1])

        with obs_core_col:
            st.markdown("**Core zone**")
            for fk in CORE_FIELDS:
                st.markdown(
                    _badge(fk, FIELD_LABELS[fk], latest_row.get(fk)),
                    unsafe_allow_html=True,
                )

        with obs_buf_col:
            st.markdown("**Buffer zone**")
            for fk in BUFFER_FIELDS:
                st.markdown(
                    _badge(fk, FIELD_LABELS[fk], latest_row.get(fk)),
                    unsafe_allow_html=True,
                )

        with obs_img_col:
            img_path = latest_row.get("rgb_core_path")
            if img_path and Path(img_path).exists():
                st.image(img_path, caption="RGB core (15 km)", use_container_width=True)
            else:
                st.markdown(_unavailable_tile("RGB core"), unsafe_allow_html=True)

# ═════════════════════════════════════════════════════════════════════════════
# TAB 3 — Model Evaluation
# ═════════════════════════════════════════════════════════════════════════════

with tab_eval:
    st.subheader("Model comparison — test set (n=30, all 10 fields)")

    if eval_data is None:
        st.warning(
            "No `comparison.json` found. "
            "Run `python scripts/compare_models.py --limit 30` first."
        )
    else:
        claude_m    = eval_data.get("claude",    {}).get("metrics", {})
        base_m      = eval_data.get("base",      {}).get("metrics", {})
        finetuned_m = eval_data.get("finetuned", {}).get("metrics", {})

        cf = claude_m.get("fields",    {})
        bf = base_m.get("fields",      {})
        ff = finetuned_m.get("fields", {})

        base_ov = base_m.get("overall", 0)
        ft_ov   = finetuned_m.get("overall", 0)

        # ── Three headline metrics ────────────────────────────────────────────
        k1, k2, k3 = st.columns(3)
        with k1:
            st.metric(
                "Claude oracle",
                f"{claude_m.get('overall', 0):.1%}",
                f"n={claude_m.get('n', 0)}",
            )
        with k2:
            st.metric(
                "Base LFM2.5-VL-450M",
                f"{base_ov:.1%}",
                f"n={base_m.get('n', 0)}",
            )
        with k3:
            st.metric(
                "AquaVeritas fine-tuned",
                f"{ft_ov:.1%}",
                f"Δ {ft_ov - base_ov:+.1%} vs base",
            )

        st.divider()

        # ── Model lift — one claim, one chart ─────────────────────────────────
        st.markdown("**Model lift — fine-tuned vs base LFM**")
        st.caption("Positive bars = accuracy gained by fine-tuning; sorted by impact.")

        delta_rows = []
        for fk in CORE_FIELDS + BUFFER_FIELDS:
            bv = bf.get(fk, 0)
            fv = ff.get(fk, 0)
            delta_rows.append({
                "Field":       FIELD_LABELS[fk],
                "Zone":        "Core" if fk in CORE_FIELDS else "Buffer",
                "Δ accuracy":  fv - bv,
                "Base LFM":    bv,
                "Fine-tuned":  fv,
            })
        delta_df = pd.DataFrame(delta_rows).sort_values("Δ accuracy", ascending=True)

        fig_delta = px.bar(
            delta_df,
            x="Δ accuracy",
            y="Field",
            orientation="h",
            color="Δ accuracy",
            color_continuous_scale=[[0, CLR_RED], [0.5, "#444444"], [1, CLR_GREEN]],
            color_continuous_midpoint=0,
            hover_data={"Base LFM": ":.1%", "Fine-tuned": ":.1%", "Δ accuracy": "+.1%"},
            labels={"Δ accuracy": "Accuracy lift vs base LFM", "Field": ""},
            height=400,
        )
        fig_delta.update_xaxes(
            tickformat="+.0%",
            zeroline=True,
            zerolinecolor="rgba(255,255,255,0.06)",
            zerolinewidth=1,
        )
        fig_delta.update_coloraxes(showscale=False)
        fig_delta.update_layout(
            margin=dict(l=0, r=20, t=10, b=0),
            yaxis=dict(tickfont=dict(size=11)),
        )
        st.plotly_chart(fig_delta, use_container_width=True)

        st.divider()

        # ── Fine-tuned vs Claude oracle — radar ───────────────────────────────
        st.markdown("**Fine-tuned vs Claude oracle**")

        labels  = [FIELD_LABELS[fk] for fk in CORE_FIELDS + BUFFER_FIELDS]
        ft_vals = [ff.get(fk, 0) for fk in CORE_FIELDS + BUFFER_FIELDS]
        cl_vals = [cf.get(fk, 0) for fk in CORE_FIELDS + BUFFER_FIELDS]

        fig_r = go.Figure()
        fig_r.add_trace(go.Scatterpolar(
            r=cl_vals + [cl_vals[0]], theta=labels + [labels[0]],
            fill="toself", name="Claude oracle",
            line_color=CLR_ORACLE,
            fillcolor="rgba(92,133,214,0.15)",
        ))
        fig_r.add_trace(go.Scatterpolar(
            r=ft_vals + [ft_vals[0]], theta=labels + [labels[0]],
            fill="toself", name="AquaVeritas fine-tuned",
            line_color=CLR_TEAL,
            fillcolor="rgba(46,196,182,0.15)",
        ))
        fig_r.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 1], tickformat=".0%")),
            showlegend=True,
            height=450,
            margin=dict(l=60, r=60, t=30, b=30),
        )
        st.plotly_chart(fig_r, use_container_width=True)

# ═════════════════════════════════════════════════════════════════════════════
# TAB 4 — Live Prediction
# ═════════════════════════════════════════════════════════════════════════════

with tab_live:
    st.subheader("Live satellite prediction")
    st.caption(
        "Select a water body — the latest cloud-free Sentinel-2 imagery is fetched "
        "automatically and the on-board model runs immediately."
    )

    llama_url = os.getenv("LLAMA_SERVER_URL", "http://localhost:8080")
    server_ok = _check_llama(llama_url)

    stat_col, simsat_col = st.columns(2)
    with stat_col:
        if server_ok:
            st.success(f"Model server ready — {llama_url}")
        else:
            st.error(
                f"Model server not reachable at **{llama_url}**\n\n"
                "```\nllama-server \\\n"
                "  -m data/models/aquaveritas-lfm-q8_0.gguf \\\n"
                "  --mmproj data/models/mmproj-LFM2.5-VL-450m-F16.gguf \\\n"
                "  --port 8080 --ctx-size 8192 -ngl 99\n```"
            )
    with simsat_col:
        try:
            from aquaveritas.simsat import SimSatClient as _SC
            _pos = _SC().get_current_position()
            _lon, _lat, _alt = _pos["lon-lat-alt"]
            st.info(f"SimSat — ({_lon:.1f}°, {_lat:.1f}°) at {_alt:.0f} km")
        except Exception:
            st.warning("SimSat not reachable")

    st.divider()

    # ── Synced location — sidebar selectbox (key="selected_id") owns the state ─
    if not selected_loc:
        st.info("Select a water body from the sidebar to run a live prediction.")
        st.stop()
    live_loc_id = selected_id
    live_loc    = selected_loc

    info_col, map_col = st.columns([1, 2])

    with info_col:
        # Show which location is active — sidebar is the single control
        st.markdown(f"### {location_names[live_loc_id]}")
        st.caption("← Change water body in the sidebar to switch location")

        if live_loc:
            st.markdown(
                f"**{live_loc.lat:.3f}°N, {live_loc.lon:.3f}°E**  \n"
                f"{live_loc.description}  \n"
                f"Expected: {live_loc.expected_water_status}"
            )

        st.divider()
        fetch_btn = st.button(
            "Fetch latest imagery & predict",
            type="primary",
            disabled=not server_ok,
            use_container_width=True,
            help="Fetches the best cloud-free Sentinel-2 tile within a 30-day window",
        )

    with map_col:
        if live_loc and _MAPBOX_TOKEN:
            st.image(
                _mapbox_satellite_url(live_loc.lon, live_loc.lat),
                caption=f"{location_names[live_loc_id]} — satellite view",
                use_container_width=True,
            )
        elif live_loc:
            st.info("Add MAPBOX_TOKEN to .env for satellite context view")

    if fetch_btn and live_loc:
        from datetime import datetime, timezone
        from aquaveritas.simsat import SimSatClient, RGB_BANDS, SWIR_BANDS, CORE_KM, BUFFER_KM
        from aquaveritas.evaluator import LlamaBackend

        timestamp = datetime.now(timezone.utc).isoformat()
        client    = SimSatClient()
        backend   = LlamaBackend(base_url=llama_url)

        prog = st.progress(0, text="Fetching Sentinel-2 imagery…")

        with st.spinner("Running inference pipeline…"):
            prog.progress(10, text="RGB core — fetching…")
            rgb_core = client.fetch_sentinel(
                live_loc.lon, live_loc.lat, timestamp, RGB_BANDS, CORE_KM)

            prog.progress(30, text="SWIR core — fetching…")
            swir_core = client.fetch_sentinel(
                live_loc.lon, live_loc.lat, timestamp, SWIR_BANDS, CORE_KM)

            prog.progress(50, text="RGB buffer — fetching…")
            rgb_buf = client.fetch_sentinel(
                live_loc.lon, live_loc.lat, timestamp, RGB_BANDS, BUFFER_KM)

            prog.progress(70, text="SWIR buffer — fetching…")
            swir_buf = client.fetch_sentinel(
                live_loc.lon, live_loc.lat, timestamp, SWIR_BANDS, BUFFER_KM)

            # ── Cloud screening ───────────────────────────────────────────────
            from aquaveritas.prose import (
                estimate_cloud_fraction, CLOUD_FRACTION_WARN, CLOUD_FRACTION_BLOCK
            )
            cloud_core = estimate_cloud_fraction(rgb_core.image) if rgb_core.available else 1.0
            cloud_buf  = estimate_cloud_fraction(rgb_buf.image)  if rgb_buf.available  else 1.0
            cloud_frac = max(cloud_core, cloud_buf)
            cloud_pct  = int(cloud_frac * 100)
            cloud_degraded = False

            if cloud_frac >= CLOUD_FRACTION_BLOCK:
                prog.progress(100, text="Imagery too degraded")
                st.error(
                    f"Cloud cover {cloud_pct}% — imagery too degraded for reliable "
                    "classification. Observation skipped."
                )
                st.stop()
            elif cloud_frac >= CLOUD_FRACTION_WARN:
                st.warning(f"Cloud cover {cloud_pct}% — low-confidence imagery. Assessment line suppressed.")
                cloud_degraded = True
            else:
                st.success(f"Cloud cover {cloud_pct}% — clear for inference.")

            prog.progress(80, text="Core zone — running inference…")
            core_result = None
            if rgb_core.available and swir_core.available:
                try:
                    core_result = backend.infer_core(
                        rgb_core.image, swir_core.image, live_loc)
                except Exception as exc:
                    st.error(f"Core inference error: {exc}")

            prog.progress(92, text="Buffer zone — running inference…")
            buffer_result = None
            if rgb_buf.available and swir_buf.available:
                try:
                    buffer_result = backend.infer_buffer(
                        rgb_buf.image, swir_buf.image, live_loc)
                except Exception as exc:
                    st.error(f"Buffer inference error: {exc}")

            prog.progress(100, text="Predictions ready")

        st.session_state["live_result"] = {
            "loc_id":          live_loc_id,
            "timestamp":       timestamp,
            "rgb_core":        rgb_core,
            "swir_core":       swir_core,
            "rgb_buf":         rgb_buf,
            "swir_buf":        swir_buf,
            "core_result":     core_result,
            "buffer_result":   buffer_result,
            "cloud_degraded":  cloud_degraded,
        }

    res = st.session_state.get("live_result")
    if res and res["loc_id"] == live_loc_id:
        st.divider()

        acq_date = (
            res["rgb_core"].metadata.get("date")
            or res["rgb_core"].metadata.get("acquisition_date")
            or res["timestamp"][:10]
        )
        import time as _time
        _fetched_at = res["timestamp"][:16]
        st.markdown(
            f"**{location_names[live_loc_id]}** — "
            f"Sentinel-2 acquisition `{acq_date}` · "
            f"Fetched `{_fetched_at} UTC`"
        )

        img_cols = st.columns(4)
        pairs = [
            ("RGB core",    res["rgb_core"]),
            ("SWIR core",   res["swir_core"]),
            ("RGB buffer",  res["rgb_buf"]),
            ("SWIR buffer", res["swir_buf"]),
        ]
        for col, (label, result) in zip(img_cols, pairs):
            with col:
                if result.available and result.image:
                    st.image(result.image, caption=label, use_container_width=True)
                else:
                    st.markdown(_unavailable_tile(label), unsafe_allow_html=True)

        st.divider()
        pred_core_col, pred_buf_col = st.columns(2)

        with pred_core_col:
            st.markdown("**Core zone — water body**")
            if res["core_result"]:
                for fk in CORE_FIELDS:
                    st.markdown(
                        _badge(fk, FIELD_LABELS[fk], res["core_result"].get(fk)),
                        unsafe_allow_html=True,
                    )
            elif not res["rgb_core"].available:
                st.warning("No cloud-free tile available for this location")
            else:
                st.error("Core inference returned no result")

        with pred_buf_col:
            st.markdown("**Buffer zone — agriculture**")
            if res["buffer_result"]:
                for fk in BUFFER_FIELDS:
                    st.markdown(
                        _badge(fk, FIELD_LABELS[fk], res["buffer_result"].get(fk)),
                        unsafe_allow_html=True,
                    )
            elif not res["rgb_buf"].available:
                st.warning("No buffer tile available")
            else:
                st.error("Buffer inference returned no result")

        with st.expander("Raw model output"):
            st.json({"core": res["core_result"], "buffer": res["buffer_result"]})

        # ── Analyst prose brief ───────────────────────────────────────────────
        if res["core_result"] or res["buffer_result"]:
            st.divider()
            with st.spinner("Generating analyst brief…"):
                from aquaveritas.prose import generate_prose
                prose = generate_prose(
                    location=location_names[live_loc_id],
                    date=acq_date,
                    core=res["core_result"],
                    buffer=res["buffer_result"],
                    cloud_degraded=res.get("cloud_degraded", False),
                )
            if prose and str(prose).strip() not in ("", "None"):
                st.markdown("**Analyst Brief**")
                st.markdown(prose)

        st.divider()
        if st.button("Save observation to database", key="save_live"):
            try:
                db = Database()
                img_dir = (
                    Path(__file__).parent.parent / "data" / "images"
                    / live_loc_id / res["timestamp"][:16].replace(":", "-")
                )
                img_dir.mkdir(parents=True, exist_ok=True)

                paths = {}
                for path_key, result in [
                    ("rgb_core_path",    res["rgb_core"]),
                    ("swir_core_path",   res["swir_core"]),
                    ("rgb_buffer_path",  res["rgb_buf"]),
                    ("swir_buffer_path", res["swir_buf"]),
                ]:
                    if result.available and result.image:
                        dest = img_dir / f"{path_key.replace('_path', '')}.png"
                        dest.write_bytes(result.image)
                        paths[path_key] = str(dest)
                    else:
                        paths[path_key] = None

                obs_id = db.insert_observation(
                    location_id=live_loc_id,
                    observed_at=res["timestamp"],
                    sat_lon=live_loc.lon,
                    sat_lat=live_loc.lat,
                    sat_alt_km=0.0,
                    core_footprint=None,
                    buffer_footprint=None,
                    image_quality_limited=False,
                    **paths,
                )
                if obs_id != -1:
                    db.apply_labels(obs_id, res["core_result"], res["buffer_result"])
                    st.success(f"Saved as observation #{obs_id} — visible in Global Monitor")
                    st.cache_data.clear()
                else:
                    st.warning("An observation already exists for this timestamp")
            except Exception as exc:
                st.error(f"Save failed: {exc}")

# ── Footer ────────────────────────────────────────────────────────────────────

st.divider()
st.caption("AquaVeritas · LFM2.5-VL-450M · SimSat + Sentinel-2 · Hack #05: AI in Space")
