"""
AquaVeritas — HuggingFace Space
---------------------------------
Two tabs:
  Global Monitor  — world map + per-location time series + latest observation card
  Dataset         — browse and filter the full observation history

Data is served from a bundled SQLite file (data/observations.db).
Live inference (LFM2.5-VL-450M + llama-server) runs locally — see SETUP.md.

Run locally:
    streamlit run hf_space/app.py
"""

import os
import sys
from html import escape as _html_escape
from pathlib import Path

import pandas as pd
import plotly.express as px
import pydeck as pdk
import streamlit as st

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "src"))

from aquaveritas.locations import LOCATIONS, LOCATIONS_BY_ID
from db_lite import DatabaseLite

# ── Mapbox — HF secret injected as MAPBOX_TOKEN env var ──────────────────────
# pydeck reads MAPBOX_API_KEY natively; set both so tile rendering works.

_MAPBOX_TOKEN = os.getenv("MAPBOX_TOKEN", "").strip()
if _MAPBOX_TOKEN:
    os.environ["MAPBOX_API_KEY"] = _MAPBOX_TOKEN
    pdk.settings.mapbox_key = _MAPBOX_TOKEN

MAP_STYLE = (
    "mapbox://styles/mapbox/light-v11"
    if _MAPBOX_TOKEN
    else "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
)

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

.stTabs [data-baseweb="tab-list"] { gap: 0; border-bottom: 2px solid #D8DDE6; }
.stTabs [data-baseweb="tab"] {
    font-weight: 600; font-size: 0.875rem; color: #706E6B;
    padding: 0.625rem 1.25rem;
    border-bottom: 2px solid transparent; margin-bottom: -2px;
    background: transparent !important;
}
.stTabs [aria-selected="true"] {
    color: #00A1E0 !important; border-bottom-color: #00A1E0 !important;
}

.stButton > button {
    font-family: 'Nunito Sans', sans-serif !important;
    font-weight: 600;
    background-color: #00A1E0 !important; color: #FFFFFF !important;
    border: none !important; border-radius: 4px !important;
    transition: background-color 0.15s ease;
}
.stButton > button:hover { background-color: #0088C7 !important; }

[data-testid="metric-container"] label {
    font-size: 0.7rem; text-transform: uppercase;
    letter-spacing: 0.07em; color: #706E6B !important; font-weight: 600;
}
[data-testid="stMetricValue"] { color: #032D60 !important; font-weight: 700 !important; }

h1, h2, h3, h4 {
    font-family: 'Nunito Sans', sans-serif !important;
    color: #032D60 !important; font-weight: 700 !important;
}

[data-testid="stDataFrame"] th {
    background: #F4F6F9 !important; color: #032D60 !important;
    font-weight: 700 !important; font-size: 0.78rem;
    text-transform: uppercase; letter-spacing: 0.06em;
}

[data-baseweb="select"] > div, [data-baseweb="input"] > div {
    border-color: #D8DDE6 !important; border-radius: 4px !important;
}
[data-baseweb="select"] > div:focus-within,
[data-baseweb="input"] > div:focus-within {
    border-color: #00A1E0 !important;
    box-shadow: 0 0 0 2px rgba(0,161,224,0.2) !important;
}
</style>
""", unsafe_allow_html=True)

# ── Design tokens — Cloud Tower design system ─────────────────────────────────

CLR_SURFACE  = "#FFFFFF"
CLR_BORDER   = "#D8DDE6"
CLR_TEXT_PRI = "#032D60"
CLR_TEXT_SEC = "#706E6B"

CLR_RED    = "#C23934"
CLR_AMBER  = "#FF9A3C"
CLR_YELLOW = "#F5C518"
CLR_GREEN  = "#04844B"
CLR_GREY   = "#706E6B"
CLR_BLUE   = "#00A1E0"
CLR_TEAL   = "#00A1E0"

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
LOCATION_NAMES = {loc.id: loc.name for loc in LOCATIONS}

CORE_FIELDS = [
    "water_extent_status", "flood_risk", "water_clarity", "shoreline_encroachment",
]
BUFFER_FIELDS = [
    "agriculture_present", "crop_stress_level", "crop_stress_type",
    "cultivation_expanding_toward_water", "settlement_visible", "bare_soil_expansion",
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
        f'</span></div>'
    )


# ── Data loading ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def load_all_observations() -> list[dict]:
    try:
        return DatabaseLite().get_observations_for_dashboard()
    except Exception as exc:
        st.error(f"Data error: {exc}")
        return []


@st.cache_data(ttl=300)
def load_latest() -> list[dict]:
    try:
        return DatabaseLite().get_latest_per_location()
    except Exception:
        return []


def to_df(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if "observed_at" in df.columns:
        df["observed_at"] = pd.to_datetime(df["observed_at"], format="ISO8601", utc=True)
    return df


# ── Load data ─────────────────────────────────────────────────────────────────

all_rows  = load_all_observations()
latest    = load_latest()
all_df    = to_df(all_rows)
latest_df = to_df(latest)
has_data  = not all_df.empty

# ── Header ────────────────────────────────────────────────────────────────────

st.title("AquaVeritas")
st.caption(
    "On-board satellite freshwater monitoring — "
    "Fine-tuned LFM2.5-VL-450M · 20 global sites · "
    "Liquid AI x DPhi Space Hackathon #05"
)
st.markdown(
    f'<p style="color:{CLR_TEXT_SEC};font-size:0.82em;margin:-4px 0 12px;">'
    '<a href="https://huggingface.co/Arty1001/aquaveritas-lfm-GGUF" target="_blank">Model</a>'
    " &nbsp;·&nbsp; "
    '<a href="https://github.com/devleks/AquaVeritas" target="_blank">Code</a>'
    " &nbsp;·&nbsp; "
    '<a href="https://huggingface.co/datasets/Arty1001/aquaveritas-water-stress" target="_blank">Dataset</a>'
    " &nbsp;·&nbsp; "
    "Live inference runs locally — see "
    '<a href="https://github.com/devleks/AquaVeritas/blob/main/SETUP.md" target="_blank">SETUP.md</a>'
    "</p>",
    unsafe_allow_html=True,
)

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Controls")
    _ALL = "__all__"
    selected_id = st.selectbox(
        "Water body",
        options=[_ALL] + list(LOCATION_NAMES.keys()),
        format_func=lambda x: "— All sites —" if x == _ALL else LOCATION_NAMES[x],
        key="selected_id",
    )
    selected_loc = LOCATIONS_BY_ID.get(selected_id) if selected_id != _ALL else None
    if selected_loc:
        st.caption(f"{selected_loc.lat:.3f}°N, {selected_loc.lon:.3f}°E")
    st.divider()
    st.metric("Total observations",  len(all_df) if has_data else 0)
    st.metric("Sites monitored", len(LOCATIONS))
    st.divider()
    st.caption(
        "Live prediction (LFM2.5-VL-450M + llama-server) "
        "runs on local hardware only. "
        "This Space shows historical observations from the monitoring pipeline."
    )

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_monitor, tab_data = st.tabs(["Global Monitor", "Dataset"])

# ═════════════════════════════════════════════════════════════════════════════
# TAB 1 — Global Monitor
# ═════════════════════════════════════════════════════════════════════════════

with tab_monitor:
    col_map, col_legend = st.columns([3, 1])

    with col_map:
        st.subheader("Global Water Body Status")

        view = pdk.ViewState(
            latitude=selected_loc.lat if selected_loc else 15,
            longitude=selected_loc.lon if selected_loc else 30,
            zoom=6 if selected_loc else 1.9,
            pitch=0,
            bearing=0,
            transition_duration=800,
        )

        # All 20 locations merged with latest observations
        all_locs_df = pd.DataFrame([
            {"location_id": l.id, "name": l.name, "lat": l.lat, "lon": l.lon}
            for l in LOCATIONS
        ])
        if not latest_df.empty:
            loc_col = "location_name" if "location_name" in latest_df.columns else "name"
            obs_slim = latest_df[
                ["location_id", "water_extent_status", "flood_risk", "crop_stress_level"]
            ].copy()
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
            lambda c: [c[0], c[1], c[2], 40]
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
            radius_min_pixels=9,
            radius_max_pixels=22,
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
            radius_max_pixels=11,
            pickable=True,
            stroked=True,
            get_line_color=[255, 255, 255, 240],
            line_width_min_pixels=1,
        )
        layer_text = pdk.Layer(
            "TextLayer",
            data=map_data,
            get_position=["lon", "lat"],
            get_text="name",
            get_size=13,
            get_color=[20, 20, 20, 230],
            get_anchor="'middle'",
            get_alignment_baseline="'top'",
            get_pixel_offset=[0, 12],
            billboard=True,
        )

        st.pydeck_chart(
            pdk.Deck(
                layers=[layer_halo, layer_dots, layer_text],
                initial_view_state=view,
                tooltip={"text": "{tooltip_text}"},
                map_style=MAP_STYLE,
            ),
            use_container_width=True,
            height=500,
        )

        if not has_data:
            st.info("No observations in the bundled dataset. All 20 monitored sites are shown.")

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

    # Sustained shrinkage alerts
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
                name = LOCATION_NAMES.get(loc_id, loc_id)
                with alert_cols[i]:
                    st.markdown(
                        f'<div style="background:rgba(220,50,50,0.12);border:1px solid rgba(220,50,50,0.3);'
                        f'border-radius:8px;padding:10px 12px;">'
                        f'<div style="color:{CLR_RED};font-size:0.72em;text-transform:uppercase;'
                        f'letter-spacing:0.06em;">{count} consecutive</div>'
                        f'<div style="color:{CLR_TEXT_PRI};font-weight:600;margin-top:2px;">{_html_escape(name)}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

    # Per-location detail
    st.divider()

    if not selected_loc:
        st.info("Select a water body from the sidebar to view location detail.")
    else:
        st.subheader(LOCATION_NAMES[selected_id])

        loc_df = (
            all_df[all_df["location_id"] == selected_id].copy()
            if has_data else pd.DataFrame()
        )

        if loc_df.empty:
            st.info(f"No observations recorded for {LOCATION_NAMES[selected_id]}.")
        else:
            col_water, col_crop = st.columns(2)

            with col_water:
                st.markdown("**Water body status over time**")
                water_order = ["flooded", "recovering", "stable", "shrinking", "dry"]
                fig = px.scatter(
                    loc_df, x="observed_at", y="water_extent_status",
                    color="flood_risk",
                    color_discrete_map={
                        "none": "#4CAF50", "elevated": "#FF9800", "active": "#F44336"
                    },
                    category_orders={"water_extent_status": water_order},
                    labels={"observed_at": "Date", "water_extent_status": "Status"},
                    height=280,
                )
                fig.update_traces(marker_size=8)
                fig.update_layout(margin=dict(l=0, r=0, t=10, b=0))
                st.plotly_chart(fig, use_container_width=True)

            with col_crop:
                st.markdown("**Crop stress level over time**")
                loc_df["stress_num"] = loc_df["crop_stress_level"].map(STRESS_NUMERIC)
                fig2 = px.scatter(
                    loc_df.dropna(subset=["stress_num"]),
                    x="observed_at", y="stress_num",
                    color="crop_stress_type",
                    color_discrete_map={
                        "drought": "#FF6B35", "flood_damage": "#4FC3F7", "none": "#81C784"
                    },
                    labels={"observed_at": "Date", "stress_num": "Stress level"},
                    height=280,
                )
                fig2.update_yaxes(
                    tickvals=[0, 1, 2, 3],
                    ticktext=["None", "Low", "Moderate", "Severe"],
                )
                fig2.update_traces(marker_size=8)
                fig2.update_layout(margin=dict(l=0, r=0, t=10, b=0))
                st.plotly_chart(fig2, use_container_width=True)

            # Latest observation card with badges
            st.markdown("**Latest observation**")
            latest_row = loc_df.sort_values("observed_at").iloc[-1]

            ts = latest_row.get("observed_at")
            st.caption(f"Observed {str(ts)[:10] if ts else '—'}")

            badge_core, badge_buf = st.columns(2)
            with badge_core:
                st.markdown("**Core zone**")
                for fk in CORE_FIELDS:
                    val = latest_row.get(fk)
                    st.markdown(_badge(fk, FIELD_LABELS[fk], val), unsafe_allow_html=True)
            with badge_buf:
                st.markdown("**Buffer zone**")
                for fk in BUFFER_FIELDS:
                    val = latest_row.get(fk)
                    if val is None:
                        val = latest_row.get(
                            "cultivation_expanding" if fk == "cultivation_expanding_toward_water" else fk
                        )
                    st.markdown(_badge(fk, FIELD_LABELS[fk], val), unsafe_allow_html=True)

            prose = latest_row.get("prose_brief")
            if prose and str(prose).strip() not in ("", "None"):
                st.divider()
                st.markdown("**Analyst Brief**")
                st.markdown(prose)


# ═════════════════════════════════════════════════════════════════════════════
# TAB 2 — Dataset
# ═════════════════════════════════════════════════════════════════════════════

with tab_data:
    st.subheader("Observation Dataset")
    st.caption(
        "All labeled observations from the AquaVeritas monitoring pipeline. "
        "Full dataset with training images: "
        "[Arty1001/aquaveritas-water-stress](https://huggingface.co/datasets/Arty1001/aquaveritas-water-stress)"
    )

    if not has_data:
        st.info("No observations in the bundled dataset.")
    else:
        f1, f2, f3 = st.columns(3)
        with f1:
            site_filter = st.multiselect(
                "Site",
                options=sorted(all_df["location_name"].unique()),
                default=[],
                placeholder="All sites",
            )
        with f2:
            status_filter = st.multiselect(
                "Water status",
                options=sorted(all_df["water_extent_status"].dropna().unique()),
                default=[],
                placeholder="All statuses",
            )
        with f3:
            stress_filter = st.multiselect(
                "Crop stress",
                options=sorted(all_df["crop_stress_level"].dropna().unique()),
                default=[],
                placeholder="All levels",
            )

        filtered = all_df.copy()
        if site_filter:
            filtered = filtered[filtered["location_name"].isin(site_filter)]
        if status_filter:
            filtered = filtered[filtered["water_extent_status"].isin(status_filter)]
        if stress_filter:
            filtered = filtered[filtered["crop_stress_level"].isin(stress_filter)]

        st.markdown(f"**{len(filtered):,} observations**")

        display_cols = [
            c for c in [
                "observed_at", "location_name", "category",
                "water_extent_status", "flood_risk", "water_clarity",
                "crop_stress_level", "crop_stress_type",
                "cultivation_expanding", "bare_soil_expansion",
                "image_quality_limited",
            ] if c in filtered.columns
        ]
        st.dataframe(
            filtered[display_cols].sort_values("observed_at", ascending=False),
            use_container_width=True,
            height=480,
        )

        st.divider()
        col_s1, col_s2 = st.columns(2)

        with col_s1:
            st.markdown("**Water status distribution**")
            status_counts = filtered["water_extent_status"].value_counts().reset_index()
            fig_s = px.bar(
                status_counts,
                x="water_extent_status", y="count",
                color="water_extent_status",
                color_discrete_map={
                    "shrinking": CLR_RED, "stable": CLR_YELLOW,
                    "flooded": CLR_BLUE, "recovering": CLR_GREEN, "dry": CLR_GREY,
                },
                height=300,
                labels={"water_extent_status": "Status", "count": "Count"},
            )
            fig_s.update_layout(showlegend=False, margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig_s, use_container_width=True)

        with col_s2:
            st.markdown("**Observations per site**")
            site_counts = (
                filtered.groupby("location_name")
                .size()
                .reset_index(name="count")
                .sort_values("count", ascending=True)
            )
            fig_l = px.bar(
                site_counts, x="count", y="location_name", orientation="h",
                height=300,
                labels={"count": "Observations", "location_name": "Site"},
            )
            fig_l.update_layout(margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig_l, use_container_width=True)


# ── Footer ────────────────────────────────────────────────────────────────────

st.divider()
st.caption(
    "AquaVeritas · Fine-tuned LFM2.5-VL-450M via SimSat + Sentinel-2 · "
    "Accuracy: 38% (base) → 84% (fine-tuned) · "
    "Liquid AI x DPhi Space Hackathon #05"
)
