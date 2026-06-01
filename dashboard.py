"""
Judicial Analytics Dashboard — Enhanced
=======================================
Adds:
  - Circuit Map views  (choropleth + bubble maps by US federal circuit)
  - Quarterly temporal analytics  (backlog evolution, clearance rate, inflow/outflow,
    duration trends, and court-level backlog by quarter)

Style mirrors the original dashboard exactly; new pages/sections are additive.
"""

from pathlib import Path

import json
import os

import duckdb
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


# =============================================================================
# Page config
# =============================================================================

st.set_page_config(
    page_title="Judicial Analytics Dashboard",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# =============================================================================
# Paths
# =============================================================================

BASE_DIR = Path(__file__).resolve().parent.parent
GOLD_DIR = BASE_DIR / "gold" / "metrics"


# =============================================================================
# Visual helpers and color semantics
# =============================================================================

COLORS = {
    "backlog":   "#ff7f0e",
    "active":    "#1f77b4",
    "resolved":  "#2ca02c",
    "duration":  "#9467bd",
    "warning":   "#ffbf00",
    "clearance": "#d62728",
    "inflow":    "#1f77b4",
    "outflow":   "#2ca02c",
}

# US Federal Circuit → representative state for centroid (for bubble map)
CIRCUIT_CENTROIDS = {
    "1":  {"lat": 42.36,  "lon": -71.06,  "label": "1st Circuit",  "states": "ME, MA, NH, RI, PR"},
    "2":  {"lat": 40.71,  "lon": -74.01,  "label": "2nd Circuit",  "states": "CT, NY, VT"},
    "3":  {"lat": 39.95,  "lon": -75.17,  "label": "3rd Circuit",  "states": "DE, NJ, PA, VI"},
    "4":  {"lat": 38.89,  "lon": -77.03,  "label": "4th Circuit",  "states": "MD, NC, SC, VA, WV"},
    "5":  {"lat": 29.76,  "lon": -95.37,  "label": "5th Circuit",  "states": "LA, MS, TX"},
    "6":  {"lat": 39.10,  "lon": -84.51,  "label": "6th Circuit",  "states": "KY, MI, OH, TN"},
    "7":  {"lat": 41.88,  "lon": -87.63,  "label": "7th Circuit",  "states": "IL, IN, WI"},
    "8":  {"lat": 44.98,  "lon": -93.27,  "label": "8th Circuit",  "states": "AR, IA, MN, MO, NE, ND, SD"},
    "9":  {"lat": 37.77,  "lon": -122.42, "label": "9th Circuit",  "states": "AK, AZ, CA, HI, ID, MT, NV, OR, WA, GU, MP"},
    "10": {"lat": 39.74,  "lon": -104.98, "label": "10th Circuit", "states": "CO, KS, NM, OK, UT, WY"},
    "11": {"lat": 33.75,  "lon": -84.39,  "label": "11th Circuit", "states": "AL, FL, GA"},
    "dc": {"lat": 38.91,  "lon": -77.04,  "label": "DC Circuit",   "states": "DC"},
    "fed":{"lat": 38.89,  "lon": -77.05,  "label": "Fed. Circuit", "states": "National"},
}

# Mapping from circuit column values → centroid keys (handles both "1" and "ca1" style)
def _norm_circuit(c: str) -> str:
    c = str(c).strip().lower()
    for key in CIRCUIT_CENTROIDS:
        if c == key or c == f"ca{key}" or c.endswith(key):
            return key
    return c


def apply_common_layout(fig: go.Figure, height: int = 420, title: str | None = None):
    layout_args = dict(
        template="plotly_white",
        height=height,
        margin=dict(l=30, r=16, t=40, b=30),
        font=dict(family="Arial", size=11),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.01,
            xanchor="right",
            x=1,
            font=dict(size=10),
        ),
    )
    if title:
        layout_args["title"] = dict(
            text=title,
            x=0.01,
            xanchor="left",
            font=dict(size=13),
        )
    fig.update_layout(**layout_args)
    return fig


def safe_read_parquet(path: Path) -> pd.DataFrame:
    try:
        return pd.read_parquet(path)
    except Exception:
        return pd.DataFrame()


# =============================================================================
# Data loaders
# =============================================================================


@st.cache_resource
def get_connection():
    return duckdb.connect()


@st.cache_data
def load_backlog():
    return safe_read_parquet(GOLD_DIR / "backlog_evolution_by_quarter.parquet")


@st.cache_data
def load_clearance():
    return safe_read_parquet(GOLD_DIR / "clearance_rate_by_quarter.parquet")


@st.cache_data
def load_court_performance():
    return safe_read_parquet(GOLD_DIR / "court_performance_metrics.parquet")


@st.cache_data
def load_case_metrics():
    return safe_read_parquet(GOLD_DIR / "case_metrics.parquet")


@st.cache_data
def load_backlog_enhanced():
    p = GOLD_DIR / "backlog_enhanced.parquet"
    return pd.read_parquet(p) if p.exists() else load_backlog()


@st.cache_data
def load_duration_quantiles():
    p = GOLD_DIR / "case_duration_distribution_circuit_by_quarter.parquet"
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()


@st.cache_data
def load_court_year_trends():
    p = GOLD_DIR / "court_year_trends.parquet"
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()


@st.cache_data
def load_active_resolved():
    p = GOLD_DIR / "active_resolved_evolution.parquet"
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()


# --- NEW loaders ---

@st.cache_data
def load_backlog_evolution_quarterly():
    """Circuit-level quarterly backlog: metrics/backlog_evolution_by_quarter.parquet"""
    p = GOLD_DIR / "backlog_evolution_by_quarter.parquet"
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()


@st.cache_data
def load_clearance_quarterly():
    """Circuit-level quarterly clearance: metrics/clearance_rate_by_quarter.parquet"""
    p = GOLD_DIR / "clearance_rate_by_quarter.parquet"
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()


@st.cache_data
def load_court_backlog_quarterly():
    """Court-level quarterly backlog/clearance ratio: court_backlog_evolution.parquet"""
    # This file is at gold root (not metrics subdir)
    candidates = [
        GOLD_DIR / "court_backlog_evolution.parquet",
        GOLD_DIR.parent / "court_backlog_evolution.parquet",
    ]
    for p in candidates:
        if p.exists():
            return pd.read_parquet(p)
    return pd.DataFrame()


@st.cache_data
def load_inflow_quarterly():
    p = GOLD_DIR / "case_inflow_by_quarter.parquet"
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()


@st.cache_data
def load_outflow_quarterly():
    p = GOLD_DIR / "case_outflow_by_quarter.parquet"
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()


@st.cache_data
def load_duration_circuit_quarterly():
    p = GOLD_DIR / "case_duration_distribution_circuit_by_quarter.parquet"
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()


@st.cache_data
def load_circuit_metrics():
    p = GOLD_DIR / "circuit_performance_metrics.parquet"
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()


@st.cache_data
def load_active_circuit_quarterly():
    p = GOLD_DIR / "active_cases_by_circuit_quarter.parquet"
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()


# =============================================================================
# Small UI helpers
# =============================================================================


def section(title: str, intro: str | None = None):
    st.divider()
    st.header(title)
    if intro:
        st.markdown(intro)


def load_checkpoint_info() -> dict:
    ck = Path(__file__).resolve().parent.parent / "logs" / "checkpoint.json"
    if ck.exists():
        try:
            return json.load(open(ck, "r", encoding="utf-8"))
        except Exception:
            return {}
    return {}


def get_layer_sizes() -> dict:
    base = Path(__file__).resolve().parent.parent
    sizes = {}
    for name in ("bronze", "silver", "gold"):
        p = base / name
        total = 0
        count = 0
        if p.exists():
            for root, dirs, files in os.walk(p):
                for f in files:
                    try:
                        fp = Path(root) / f
                        total += fp.stat().st_size
                        count += 1
                    except Exception:
                        continue
        sizes[name] = {"files": count, "bytes": total}
    return sizes


# =============================================================================
# Map helpers
# =============================================================================


def _enrich_with_geo(df: pd.DataFrame, circuit_col: str = "circuit") -> pd.DataFrame:
    """Attach lat/lon/label to circuit-level dataframe."""
    if circuit_col not in df.columns:
        return df
    rows = []
    for _, row in df.iterrows():
        key = _norm_circuit(str(row[circuit_col]))
        geo = CIRCUIT_CENTROIDS.get(key, {})
        rows.append({**row.to_dict(), **{
            "lat": geo.get("lat", np.nan),
            "lon": geo.get("lon", np.nan),
            "circuit_label": geo.get("label", str(row[circuit_col])),
            "states": geo.get("states", ""),
        }})
    return pd.DataFrame(rows).dropna(subset=["lat", "lon"])


def circuit_bubble_map(
    df: pd.DataFrame,
    size_col: str,
    color_col: str,
    title: str,
    color_scale: str = "Oranges",
    height: int = 480,
    hover_cols: list | None = None,
) -> go.Figure:
    """Build a bubble map over US federal circuits."""
    geo = _enrich_with_geo(df)
    if geo.empty:
        return go.Figure()

    size_vals = geo[size_col].fillna(0).clip(lower=0)
    # normalise bubble size; min 6, max 50
    s_min, s_max = size_vals.min(), size_vals.max()
    norm = 6 + (size_vals - s_min) / (s_max - s_min + 1e-9) * 44

    hover = hover_cols or []
    custom = geo[hover].values if hover else None
    htemplate = (
        "<b>%{text}</b><br>"
        + f"{size_col}: %{{marker.color:,.1f}}<br>"
        + "<br>".join(f"{c}: %{{customdata[{i}]}}" for i, c in enumerate(hover))
        + "<extra></extra>"
    )

    fig = go.Figure(go.Scattergeo(
        lat=geo["lat"],
        lon=geo["lon"],
        text=geo["circuit_label"],
        marker=dict(
            size=norm,
            color=geo[color_col].fillna(0),
            colorscale=color_scale,
            showscale=True,
            colorbar=dict(title=color_col, thickness=12, len=0.6),
            line=dict(width=1, color="rgba(0,0,0,0.3)"),
            opacity=0.82,
        ),
        customdata=custom,
        hovertemplate=htemplate,
        mode="markers+text",
        textposition="top center",
        textfont=dict(size=9),
    ))

    fig.update_geos(
        scope="usa",
        showland=True,
        landcolor="#f0f0f0",
        showcoastlines=True,
        coastlinecolor="#cccccc",
        showstates=True,
        statecolor="#e0e0e0",
        showlakes=False,
        projection_type="albers usa",
    )
    fig.update_layout(
        title=dict(text=title, x=0.01, font=dict(size=13)),
        height=height,
        margin=dict(l=0, r=0, t=40, b=0),
        template="plotly_white",
        font=dict(family="Arial", size=11),
    )
    return fig


# =============================================================================
# Load all data
# =============================================================================

backlog               = load_backlog()
backlog_enh           = load_backlog_enhanced()
clearance             = load_clearance()
performance           = load_court_performance()
case_metrics          = load_case_metrics()
duration_quantiles    = load_duration_quantiles()
court_year_trends     = load_court_year_trends()
active_resolved       = load_active_resolved()

# quarterly / circuit
backlog_q             = load_backlog_evolution_quarterly()
clearance_q           = load_clearance_quarterly()
court_backlog_q       = load_court_backlog_quarterly()
inflow_q              = load_inflow_quarterly()
outflow_q             = load_outflow_quarterly()
duration_circ_q       = load_duration_circuit_quarterly()
circuit_metrics       = load_circuit_metrics()
active_circ_q         = load_active_circuit_quarterly()


# =============================================================================
# Sidebar
# =============================================================================

st.sidebar.title("⚖️ Judicial Analytics")

page = st.sidebar.radio(
    "Navigation",
    [
        "Overview",
        "Backlog Analytics",
        "Circuit Maps",
        "Quarterly Analysis",
        "Court Performance",
        "Duration Analysis",
        "Raw Tables",
    ],
)

top_n = st.sidebar.slider("Top courts", min_value=5, max_value=50, value=20)

years = sorted(backlog["year"].unique()) if not backlog.empty else [2020, 2026]
min_year, max_year = int(years[0]), int(years[-1])
year_range = st.sidebar.slider("Year range", min_value=min_year, max_value=max_year, value=(min_year, max_year))

# Circuit filter (used in Circuit Maps and Quarterly Analysis)
all_circuits = []
for df in [backlog_q, clearance_q, active_circ_q, circuit_metrics]:
    if not df.empty and "circuit" in df.columns:
        all_circuits += list(df["circuit"].dropna().unique())
all_circuits = sorted(set(str(c) for c in all_circuits))
selected_circuits = st.sidebar.multiselect(
    "Circuits (maps & quarterly)", options=all_circuits, default=all_circuits
)

court_types = []
if not case_metrics.empty and "jurisdiction_type" in case_metrics.columns:
    court_types = sorted(case_metrics["jurisdiction_type"].dropna().unique())
selected_court_types = st.sidebar.multiselect("Court types", options=court_types, default=court_types)

show_active   = st.sidebar.checkbox("Show active cases",   value=True)
show_resolved = st.sidebar.checkbox("Show resolved cases", value=True)


# =============================================================================
# Main title
# =============================================================================

st.title("Judicial Analytics Dashboard")
st.caption(
    "Analytical observatory of judicial congestion, court workload, backlog accumulation, "
    "and case resolution dynamics."
)


# =============================================================================
# Overview
# =============================================================================

if page == "Overview":

    section(
        "System overview",
        """
This dashboard explores judicial workload dynamics through a Medallion-based analytical pipeline.
The objective is to monitor backlog accumulation, case resolution capacity, court-level heterogeneity,
and judicial duration patterns using longitudinal court records.

The analysis particularly focuses on:

- backlog growth and congestion dynamics,
- imbalance between incoming and resolved cases,
- variability in court performance,
- methodological challenges linked to right-censored judicial durations.
""",
    )

    total_cases    = len(case_metrics) if not case_metrics.empty else 0
    active_cases   = int(performance["active_cases"].sum())   if not performance.empty else 0
    resolved_cases = int(performance["resolved_cases"].sum()) if not performance.empty else 0

    avg_duration = (
        round(performance["mean_duration"].replace(0, pd.NA).dropna().mean(), 2)
        if not performance.empty
        else None
    )
    latest_backlog = (
        int(backlog_enh.loc[backlog_enh["year"].between(year_range[0], year_range[1]), "backlog"].iloc[-1])
        if not backlog_enh.empty
        else 0
    )
    latest_clearance = (
        round(clearance["clearance_rate_pct"].dropna().iloc[-1], 2) if not clearance.empty else None
    )

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Total cases",          f"{total_cases:,}")
    c2.metric("Active cases",         f"{active_cases:,}")
    c3.metric("Resolved cases",       f"{resolved_cases:,}")
    c4.metric("Avg duration (days)",  avg_duration)
    c5.metric("Current backlog",      f"{latest_backlog:,}")
    c6.metric("Clearance % (latest)", latest_clearance)

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Backlog evolution")
        df_plot = (
            backlog_enh[backlog_enh["year"].between(year_range[0], year_range[1])]
            if not backlog_enh.empty else pd.DataFrame()
        )
        if not df_plot.empty:
            fig = px.bar(df_plot, x="year", y="backlog", color_discrete_sequence=[COLORS["backlog"]])
            fig = apply_common_layout(fig, height=340, title="Judicial backlog over time")
            fig.update_traces(marker_line_width=0)
            st.plotly_chart(fig, use_container_width=True)
            st.caption(
                "Backlog measures the accumulation of unresolved cases over time. "
                "Sustained backlog growth suggests new filings systematically exceed judicial resolution capacity."
            )
        else:
            st.info("Backlog data not available.")

    with col2:
        st.subheader("Inflow vs Outflow")
        flow_df = (
            backlog_enh.loc[backlog_enh["year"].between(year_range[0], year_range[1]), ["year", "inflow", "outflow"]]
            if not backlog_enh.empty else pd.DataFrame()
        )
        if not flow_df.empty:
            flow_m = flow_df.melt(id_vars="year", var_name="flow_type", value_name="cases")
            color_map = {"inflow": COLORS["active"], "outflow": COLORS["resolved"]}
            fig = px.bar(flow_m, x="year", y="cases", color="flow_type", barmode="group", color_discrete_map=color_map)
            fig = apply_common_layout(fig, height=340, title="Case inflow and outflow")
            st.plotly_chart(fig, use_container_width=True)
            st.caption(
                "Comparing inflow and outflow highlights whether courts resolve cases fast enough to absorb new filings. "
                "Persistent inflow > outflow contributes directly to backlog expansion."
            )
        else:
            st.info("Inflow/outflow data not available.")

    st.subheader("Judicial congestion dynamics")
    if not backlog_enh.empty:
        df_dyn = (
            backlog_enh.sort_values("year")
            .loc[backlog_enh["year"].between(year_range[0], year_range[1])]
            .copy()
        )
        df_dyn["pressure_ratio"] = df_dyn["inflow"] / df_dyn["outflow"].replace(0, np.nan)
        fig_ratio = px.line(df_dyn, x="year", y="pressure_ratio", markers=True, color_discrete_sequence=[COLORS["backlog"]])
        fig_ratio.add_hline(y=1, line_dash="dash", line_color="#666666")
        fig_ratio = apply_common_layout(fig_ratio, height=300, title="Judicial pressure ratio (inflow / outflow)")
        fig_ratio.update_yaxes(title_text="Pressure ratio", range=[0, 10])
        st.plotly_chart(fig_ratio, use_container_width=True)
        st.caption(
            "A pressure ratio above 1 indicates that incoming cases exceed judicial resolution capacity, "
            "contributing to congestion growth."
        )
    else:
        st.info("Judicial congestion indicators are not available for the selected range.")


# =============================================================================
# Backlog Analytics
# =============================================================================

elif page == "Backlog Analytics":

    section(
        "Judicial congestion indicators",
        "Temporal indicators describing judicial congestion, backlog accumulation, and court resolution capacity.",
    )

    df_backlog = backlog.copy() if not backlog.empty else pd.DataFrame()
    if not df_backlog.empty:
        fig = px.bar(
            df_backlog.loc[df_backlog["year"].between(year_range[0], year_range[1])],
            x="year", y="backlog", color_discrete_sequence=[COLORS["backlog"]],
        )
        fig = apply_common_layout(fig, height=360, title="Backlog by year")
        fig.update_xaxes(range=[2019, 2026])
        st.plotly_chart(fig, use_container_width=True)
        st.caption("The sharp increase in backlog after 2020 suggests persistent imbalance between incoming and resolved cases.")
    else:
        st.info("Backlog data not available.")

    if not clearance.empty:
        clr = clearance.dropna(subset=["clearance_rate_pct"]).sort_values("year").copy()
        clr = clr.loc[clr["year"].between(year_range[0], year_range[1])]
        if not clr.empty:
            clr["smoothed"] = clr["clearance_rate_pct"].rolling(window=3, center=True, min_periods=1).mean()
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=clr["year"], y=clr["clearance_rate_pct"], mode="lines+markers", name="Raw clearance", line=dict(color="#888888", width=1), marker=dict(size=6, opacity=0.7)))
            fig.add_trace(go.Scatter(x=clr["year"], y=clr["smoothed"], mode="lines", name="3-year smooth", line=dict(color=COLORS["backlog"], width=3)))
            fig = apply_common_layout(fig, height=380, title="Clearance rate (raw vs 3-year smoothed)")
            fig.update_yaxes(title_text="Clearance (%)", range=[0, 200])
            st.plotly_chart(fig, use_container_width=True)
            st.caption("Clearance rates above 100% indicate periods where courts resolved more cases than they received.")

            if not duration_quantiles.empty and "sparse_year_warning" in duration_quantiles.columns:
                dq_sel = duration_quantiles.loc[duration_quantiles["year"].between(year_range[0], year_range[1])]
                if dq_sel["sparse_year_warning"].any():
                    st.caption("Sparse historical resolutions may destabilize clearance estimates.")
            else:
                st.info("Clearance rate shown with 3-year smoothing to reduce noise. Recent-year estimates are right-censored.")
        else:
            st.info("Clearance data not available for selected years.")
    else:
        st.info("Clearance data not available.")


# =============================================================================
# Circuit Maps  (NEW)
# =============================================================================

elif page == "Circuit Maps":

    section(
        "Geographic circuit distribution",
        "US federal circuit-level indicators displayed on geographic maps. "
        "Bubble size and colour encode the selected metric for each of the 13 circuits.",
    )

    # --- Build a circuit-level summary from available data ---

    # Prefer circuit_metrics (has active + avg_resolution_days),
    # fall back to aggregating from case_metrics or performance.
    if not circuit_metrics.empty:
        circ_summary = circuit_metrics.copy()
    elif not case_metrics.empty and "circuit" in case_metrics.columns:
        circ_summary = (
            case_metrics.groupby("circuit", as_index=False).agg(
                active_cases=("is_active", "sum"),
                resolved_cases=("duration_days", "count"),
                mean_duration=("duration_days", "mean"),
            )
        )
    else:
        circ_summary = pd.DataFrame()

    # Join with quarterly backlog sum if available
    if not backlog_q.empty and "circuit" in backlog_q.columns and "backlog" in backlog_q.columns:
        # Latest quarter per circuit
        bq_latest = (
            backlog_q.sort_values("year_quarter")
            .groupby("circuit", as_index=False)
            .last()[["circuit", "backlog"]]
            .rename(columns={"backlog": "latest_backlog"})
        )
        if not circ_summary.empty:
            circ_summary = circ_summary.merge(bq_latest, on="circuit", how="left")
        else:
            circ_summary = bq_latest

    if not circ_summary.empty and selected_circuits:
        circ_summary = circ_summary[circ_summary["circuit"].astype(str).isin(selected_circuits)]

    # --- Map selector ---
    map_metric = st.selectbox(
        "Metric to display on map",
        [c for c in ["active_cases", "latest_backlog", "mean_duration", "resolved_cases"] if not circ_summary.empty and c in circ_summary.columns],
    )

    color_scales = {
        "active_cases":    "Blues",
        "latest_backlog":  "Oranges",
        "mean_duration":   "Purples",
        "resolved_cases":  "Greens",
    }

    if circ_summary.empty:
        st.info("Circuit-level summary data not available. Ensure circuit_performance_metrics.parquet or case_metrics.parquet is present.")
    else:
        fig_map = circuit_bubble_map(
            df=circ_summary,
            size_col=map_metric,
            color_col=map_metric,
            title=f"US Federal Circuits — {map_metric.replace('_', ' ').title()}",
            color_scale=color_scales.get(map_metric, "Blues"),
            height=500,
        )
        st.plotly_chart(fig_map, use_container_width=True)
        st.caption(
            "Bubble size and colour both encode the selected metric. "
            "Larger/darker bubbles indicate higher values. "
            "Circuit centroids are placed at representative coordinates; they do not reflect exact court locations."
        )

    # --- Bar chart: circuit comparison ---
    st.subheader("Circuit comparison — bar chart")
    if not circ_summary.empty and map_metric in circ_summary.columns:
        bar_df = circ_summary.dropna(subset=[map_metric]).sort_values(map_metric, ascending=False)
        fig = px.bar(
            bar_df,
            x="circuit",
            y=map_metric,
            color=map_metric,
            color_continuous_scale=color_scales.get(map_metric, "Blues"),
            labels={"circuit": "Circuit", map_metric: map_metric.replace("_", " ").title()},
        )
        fig = apply_common_layout(fig, height=360, title=f"{map_metric.replace('_', ' ').title()} by Circuit")
        fig.update_coloraxes(showscale=False)
        st.plotly_chart(fig, use_container_width=True)

    # --- Multi-metric radar (spider) per circuit ---
    st.subheader("Circuit multi-metric comparison")
    radar_metrics = [c for c in ["active_cases", "latest_backlog", "mean_duration", "resolved_cases"] if not circ_summary.empty and c in circ_summary.columns]

    if len(radar_metrics) >= 3 and not circ_summary.empty:
        # Normalise 0-1 per metric for radar
        radar_df = circ_summary.copy().dropna(subset=radar_metrics)
        for m in radar_metrics:
            rng = radar_df[m].max() - radar_df[m].min()
            radar_df[f"_{m}_norm"] = (radar_df[m] - radar_df[m].min()) / (rng if rng > 0 else 1)

        fig_radar = go.Figure()
        for _, row in radar_df.iterrows():
            vals = [row[f"_{m}_norm"] for m in radar_metrics]
            vals += [vals[0]]  # close polygon
            fig_radar.add_trace(go.Scatterpolar(
                r=vals,
                theta=radar_metrics + [radar_metrics[0]],
                fill="toself",
                name=str(row["circuit"]),
                opacity=0.55,
            ))
        fig_radar.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 1])),
            template="plotly_white",
            height=460,
            legend=dict(orientation="h", y=-0.15),
            margin=dict(l=30, r=30, t=40, b=30),
            title=dict(text="Normalised circuit performance radar", x=0.01, font=dict(size=13)),
        )
        st.plotly_chart(fig_radar, use_container_width=True)
        st.caption(
            "Each axis is normalised 0–1. A larger polygon indicates relatively higher values across all metrics. "
            "Circuits with large active and backlog but low resolved cases signal persistent congestion."
        )
    else:
        st.info("Not enough metric columns for radar chart.")

    # --- Animated bubble map over time (from quarterly backlog) ---
    st.subheader("Backlog evolution by circuit — animated map")
    if not backlog_q.empty and "circuit" in backlog_q.columns and "backlog" in backlog_q.columns:
        bq_geo = _enrich_with_geo(backlog_q, circuit_col="circuit")
        if not bq_geo.empty and selected_circuits:
            bq_geo = bq_geo[bq_geo["circuit"].astype(str).isin(selected_circuits)]

        if not bq_geo.empty:
            bq_geo["backlog"] = bq_geo["backlog"].clip(lower=0)
            size_max_val = bq_geo["backlog"].max()
            bq_geo["_size"] = 6 + bq_geo["backlog"] / (size_max_val + 1) * 44

            fig_anim = px.scatter_geo(
                bq_geo.sort_values("year_quarter"),
                lat="lat",
                lon="lon",
                size="_size",
                color="backlog",
                hover_name="circuit_label",
                hover_data={"circuit": True, "backlog": True, "inflow": True, "outflow": True, "_size": False, "lat": False, "lon": False},
                animation_frame="year_quarter",
                color_continuous_scale="Oranges",
                size_max=50,
                scope="usa",
                projection="albers usa",
                title="Quarterly backlog evolution across US federal circuits",
            )
            fig_anim.update_geos(
                showland=True, landcolor="#f0f0f0",
                showcoastlines=True, coastlinecolor="#cccccc",
                showstates=True, statecolor="#e0e0e0",
            )
            fig_anim.update_layout(
                height=520,
                margin=dict(l=0, r=0, t=50, b=0),
                template="plotly_white",
                font=dict(family="Arial", size=11),
                coloraxis_colorbar=dict(title="Backlog", thickness=12),
            )
            st.plotly_chart(fig_anim, use_container_width=True)
            st.caption(
                "Use the play button or scrub the slider to observe how backlog evolved quarter by quarter across circuits. "
                "Growing bubbles signal worsening congestion."
            )
        else:
            st.info("No geo-matched circuit data available for animation.")
    else:
        st.info("Quarterly backlog data (backlog_evolution_by_quarter.parquet) not available.")


# =============================================================================
# Quarterly Analysis  (NEW)
# =============================================================================

elif page == "Quarterly Analysis":

    section(
        "Quarterly temporal analytics",
        "Quarter-resolution indicators for backlog, inflow/outflow, clearance rate, "
        "duration, and active caseload — broken down by circuit.",
    )

    # ---- Quarter range filter ----
    all_quarters: list[str] = []
    for df in [backlog_q, clearance_q, inflow_q, outflow_q]:
        qcol = next((c for c in df.columns if "quarter" in c.lower() and "year" in c.lower()), None)
        if not df.empty and qcol:
            all_quarters += list(df[qcol].dropna().unique())
    all_quarters = sorted(set(all_quarters))

    if all_quarters:
        q_min, q_max = all_quarters[0], all_quarters[-1]
        q_range = st.select_slider("Quarter range", options=all_quarters, value=(q_min, q_max))
    else:
        q_range = (None, None)
        st.info("No quarterly time dimension detected in available data.")

    def _filter_quarters(df: pd.DataFrame, qcol: str) -> pd.DataFrame:
        if q_range[0] is None or qcol not in df.columns:
            return df
        return df[df[qcol].between(q_range[0], q_range[1])].copy()

    def _filter_circuits(df: pd.DataFrame) -> pd.DataFrame:
        if "circuit" in df.columns and selected_circuits:
            return df[df["circuit"].astype(str).isin(selected_circuits)]
        return df

    # =========================================================================
    # Section 1: Backlog evolution by quarter
    # =========================================================================
    st.subheader("Quarterly backlog evolution by circuit")

    if not backlog_q.empty:
        qcol_bq = "year_quarter"
        bq = _filter_quarters(backlog_q, qcol_bq)
        bq = _filter_circuits(bq)

        if not bq.empty:
            fig = px.line(
                bq, x=qcol_bq, y="backlog", color="circuit",
                markers=True, color_discrete_sequence=px.colors.qualitative.Set2,
                labels={qcol_bq: "Quarter", "backlog": "Backlog"},
            )
            fig = apply_common_layout(fig, height=400, title="Backlog by circuit and quarter")
            fig.update_xaxes(tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)
            st.caption(
                "Each line represents a federal circuit. Diverging trajectories indicate heterogeneous congestion dynamics."
            )

            # Stacked area variant
            fig_area = px.area(
                bq.sort_values(qcol_bq),
                x=qcol_bq, y="backlog", color="circuit",
                color_discrete_sequence=px.colors.qualitative.Set2,
                labels={qcol_bq: "Quarter", "backlog": "Backlog"},
            )
            fig_area = apply_common_layout(fig_area, height=360, title="Cumulative backlog composition by circuit (stacked area)")
            fig_area.update_xaxes(tickangle=-45)
            st.plotly_chart(fig_area, use_container_width=True)
            st.caption("Stacked view shows how each circuit contributes to total system backlog over time.")
        else:
            st.info("No backlog data for selected circuits/quarters.")
    else:
        st.info("Quarterly backlog data not available (backlog_evolution_by_quarter.parquet).")

    # =========================================================================
    # Section 2: Quarterly inflow vs outflow
    # =========================================================================
    st.subheader("Quarterly inflow and outflow by circuit")

    inflow_qcol  = next((c for c in inflow_q.columns  if "quarter" in c.lower()), None)
    outflow_qcol = next((c for c in outflow_q.columns if "quarter" in c.lower()), None)

    if not inflow_q.empty and not outflow_q.empty and inflow_qcol and outflow_qcol:
        iq = _filter_quarters(inflow_q.rename(columns={inflow_qcol: "year_quarter"}), "year_quarter")
        oq = _filter_quarters(outflow_q.rename(columns={outflow_qcol: "year_quarter"}), "year_quarter")
        iq = _filter_circuits(iq)
        oq = _filter_circuits(oq)

        inflow_col  = next((c for c in iq.columns if c in ("inflow", "filed_cases", "active_cases")), None)
        outflow_col = next((c for c in oq.columns if c in ("outflow", "terminated_cases")), None)

        if inflow_col and outflow_col:
            merged_flow = iq[["year_quarter", "circuit", inflow_col]].merge(
                oq[["year_quarter", "circuit", outflow_col]],
                on=["year_quarter", "circuit"], how="outer",
            ).fillna(0)
            merged_flow.rename(columns={inflow_col: "inflow", outflow_col: "outflow"}, inplace=True)

            circuit_selector = st.selectbox("Select circuit (inflow/outflow detail)", options=sorted(merged_flow["circuit"].unique()))
            mc = merged_flow[merged_flow["circuit"] == circuit_selector].sort_values("year_quarter")

            fig = go.Figure()
            fig.add_trace(go.Bar(x=mc["year_quarter"], y=mc["inflow"],  name="Inflow",  marker_color=COLORS["inflow"],  opacity=0.8))
            fig.add_trace(go.Bar(x=mc["year_quarter"], y=mc["outflow"], name="Outflow", marker_color=COLORS["outflow"], opacity=0.8))
            fig = apply_common_layout(fig, height=380, title=f"Quarterly inflow vs outflow — Circuit {circuit_selector}")
            fig.update_layout(barmode="group")
            fig.update_xaxes(tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)

            # Net flow line
            mc["net"] = mc["inflow"] - mc["outflow"]
            fig_net = px.line(mc, x="year_quarter", y="net", markers=True, color_discrete_sequence=[COLORS["backlog"]])
            fig_net.add_hline(y=0, line_dash="dash", line_color="#666")
            fig_net = apply_common_layout(fig_net, height=260, title=f"Net case flow (inflow − outflow) — Circuit {circuit_selector}")
            fig_net.update_xaxes(tickangle=-45)
            fig_net.update_yaxes(title_text="Net cases")
            st.plotly_chart(fig_net, use_container_width=True)
            st.caption("Positive net flow means more cases filed than resolved in that quarter, adding to the backlog.")

            # Heatmap: net flow across circuits × quarters
            st.subheader("Net flow heatmap — all circuits")
            heat_df = merged_flow.copy()
            heat_df["net"] = heat_df["inflow"] - heat_df["outflow"]
            pivot = heat_df.pivot_table(index="circuit", columns="year_quarter", values="net", aggfunc="sum")
            if not pivot.empty:
                fig_heat = px.imshow(
                    pivot,
                    color_continuous_scale="RdYlGn_r",
                    aspect="auto",
                    labels=dict(x="Quarter", y="Circuit", color="Net flow"),
                    title="Net case flow heatmap (inflow − outflow) by circuit and quarter",
                )
                fig_heat.update_layout(height=380, template="plotly_white", margin=dict(l=30, r=16, t=40, b=30), font=dict(family="Arial", size=11))
                fig_heat.update_xaxes(tickangle=-45)
                st.plotly_chart(fig_heat, use_container_width=True)
                st.caption("Red cells indicate quarters where inflow substantially exceeded outflow (backlog-generating). Green cells indicate resolution surplus.")
        else:
            st.info("Could not identify inflow/outflow columns in quarterly data.")
    else:
        st.info("Quarterly inflow/outflow data not available.")

    # =========================================================================
    # Section 3: Quarterly clearance rate by circuit
    # =========================================================================
    st.subheader("Quarterly clearance rate by circuit")

    if not clearance_q.empty:
        cqcol = next((c for c in clearance_q.columns if "quarter" in c.lower()), None)
        if cqcol:
            cq = _filter_quarters(clearance_q.rename(columns={cqcol: "year_quarter"}), "year_quarter")
            cq = _filter_circuits(cq)

            if "clearance_rate_pct" not in cq.columns and "clearance_rate" in cq.columns:
                cq["clearance_rate_pct"] = (cq["clearance_rate"] * 100).round(2)

            if not cq.empty and "clearance_rate_pct" in cq.columns:
                fig = px.line(
                    cq, x="year_quarter", y="clearance_rate_pct", color="circuit",
                    markers=True, color_discrete_sequence=px.colors.qualitative.Set2,
                    labels={"year_quarter": "Quarter", "clearance_rate_pct": "Clearance (%)"},
                )
                fig.add_hline(y=100, line_dash="dash", line_color="#666", annotation_text="100%")
                fig = apply_common_layout(fig, height=400, title="Quarterly clearance rate by circuit (%)")
                fig.update_yaxes(range=[0, 250])
                fig.update_xaxes(tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)
                st.caption(
                    "Clearance rate = outflow / inflow × 100. "
                    "Values below 100% mean the circuit is accumulating backlog in that quarter."
                )

                # Box distribution of clearance per circuit
                fig_box = px.box(
                    cq.dropna(subset=["clearance_rate_pct"]),
                    x="circuit", y="clearance_rate_pct",
                    color="circuit",
                    color_discrete_sequence=px.colors.qualitative.Set2,
                    labels={"circuit": "Circuit", "clearance_rate_pct": "Clearance (%)"},
                    title="Distribution of quarterly clearance rates by circuit",
                )
                fig_box.add_hline(y=100, line_dash="dash", line_color="#666")
                fig_box = apply_common_layout(fig_box, height=380)
                fig_box.update_yaxes(range=[0, 300])
                st.plotly_chart(fig_box, use_container_width=True)
                st.caption("Box plots reveal inter-circuit dispersion. Wide boxes indicate volatile quarterly clearance performance.")
            else:
                st.info("Clearance rate column not found in quarterly data.")
        else:
            st.info("Quarter column not detected in clearance_rate_by_quarter.parquet.")
    else:
        st.info("Quarterly clearance data not available (clearance_rate_by_quarter.parquet).")

    # =========================================================================
    # Section 4: Duration trends by quarter (circuit)
    # =========================================================================
    st.subheader("Case duration trends by quarter and circuit")

    if not duration_circ_q.empty:
        dcq = _filter_quarters(duration_circ_q, "year_quarter_filed")
        dcq = _filter_circuits(dcq)

        if not dcq.empty:
            dur_metric = st.selectbox(
                "Duration metric",
                [c for c in ["mean_duration", "median_duration", "p90_duration", "p75_duration"] if c in dcq.columns],
            )
            fig = px.line(
                dcq, x="year_quarter_filed", y=dur_metric, color="circuit",
                markers=True, color_discrete_sequence=px.colors.qualitative.Set2,
                labels={"year_quarter_filed": "Filing quarter", dur_metric: dur_metric.replace("_", " ").title()},
            )
            fig = apply_common_layout(fig, height=400, title=f"Quarterly {dur_metric.replace('_', ' ')} by circuit")
            fig.update_xaxes(tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)
            st.caption(
                "Duration metrics are computed on resolved cases only. "
                "Right-censoring means recent quarters may undercount long-running cases."
            )

            # Fan chart: median ± p90 band for a single circuit
            fan_circuit = st.selectbox("Circuit for duration fan chart", options=sorted(dcq["circuit"].unique()))
            fan_df = dcq[dcq["circuit"] == fan_circuit].sort_values("year_quarter_filed")
            if "median_duration" in fan_df.columns and "p90_duration" in fan_df.columns:
                fig_fan = go.Figure()
                fig_fan.add_trace(go.Scatter(
                    x=list(fan_df["year_quarter_filed"]) + list(fan_df["year_quarter_filed"])[::-1],
                    y=list(fan_df["p90_duration"]) + [0] * len(fan_df),
                    fill="toself", fillcolor="rgba(148,103,189,0.15)", line=dict(width=0),
                    name="Up to P90", showlegend=True,
                ))
                fig_fan.add_trace(go.Scatter(
                    x=fan_df["year_quarter_filed"], y=fan_df["median_duration"],
                    mode="lines+markers", name="Median", line=dict(color=COLORS["duration"], width=2),
                ))
                if "p90_duration" in fan_df.columns:
                    fig_fan.add_trace(go.Scatter(
                        x=fan_df["year_quarter_filed"], y=fan_df["p90_duration"],
                        mode="lines", name="P90", line=dict(color=COLORS["duration"], width=1, dash="dot"),
                    ))
                fig_fan = apply_common_layout(fig_fan, height=340, title=f"Duration fan chart — Circuit {fan_circuit}")
                fig_fan.update_xaxes(tickangle=-45, title_text="Filing quarter")
                fig_fan.update_yaxes(title_text="Duration (days)")
                st.plotly_chart(fig_fan, use_container_width=True)
        else:
            st.info("No duration data for selected circuits/quarters.")
    else:
        st.info("Quarterly circuit duration data not available (case_duration_distribution_circuit_by_quarter.parquet).")

    # =========================================================================
    # Section 5: Active caseload evolution by circuit
    # =========================================================================
    st.subheader("Active caseload evolution by circuit (quarterly)")

    if not active_circ_q.empty:
        aqcol = next((c for c in active_circ_q.columns if "quarter" in c.lower()), None)
        cnt_col = next((c for c in active_circ_q.columns if "count" in c.lower() or c == "active_cases_count"), None)
        if aqcol and cnt_col:
            aq = _filter_quarters(active_circ_q.rename(columns={aqcol: "year_quarter", cnt_col: "active_count"}), "year_quarter")
            aq = _filter_circuits(aq)
            if not aq.empty:
                fig = px.area(
                    aq.sort_values("year_quarter"),
                    x="year_quarter", y="active_count", color="circuit",
                    color_discrete_sequence=px.colors.qualitative.Set2,
                    labels={"year_quarter": "Quarter", "active_count": "Active cases"},
                )
                fig = apply_common_layout(fig, height=380, title="Active caseload by circuit (stacked area)")
                fig.update_xaxes(tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)
                st.caption(
                    "Active caseload includes all cases that were open at any point during the quarter. "
                    "Sustained growth across circuits indicates system-wide congestion."
                )
        else:
            st.info("Could not detect quarter/count columns in active_cases_by_circuit_quarter.parquet.")
    else:
        st.info("Active circuit quarterly data not available (active_cases_by_circuit_quarter.parquet).")

    # =========================================================================
    # Section 6: Court-level quarterly clearance ratio
    # =========================================================================
    st.subheader("Court-level quarterly backlog clearance ratio")

    if not court_backlog_q.empty:
        cbq_qcol = next((c for c in court_backlog_q.columns if "quarter" in c.lower()), None)
        if cbq_qcol:
            cbq = _filter_quarters(court_backlog_q.rename(columns={cbq_qcol: "year_quarter"}), "year_quarter")
            if not cbq.empty and "backlog_clearance_ratio" in cbq.columns:
                # Top courts by mean clearance deficit
                court_mean = (
                    cbq.groupby("court_id")["backlog_clearance_ratio"]
                    .mean()
                    .sort_values()
                    .head(top_n)
                )
                worst_courts = court_mean.index.tolist()
                cbq_top = cbq[cbq["court_id"].isin(worst_courts)]

                fig = px.line(
                    cbq_top, x="year_quarter", y="backlog_clearance_ratio", color="court_id",
                    color_discrete_sequence=px.colors.qualitative.Alphabet,
                    labels={"year_quarter": "Quarter", "backlog_clearance_ratio": "Clearance ratio"},
                )
                fig.add_hline(y=1.0, line_dash="dash", line_color="#666", annotation_text="1.0")
                fig = apply_common_layout(fig, height=420, title=f"Quarterly clearance ratio — bottom {top_n} courts")
                fig.update_xaxes(tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)
                st.caption(
                    "Clearance ratio < 1 means the court terminated fewer cases than it received. "
                    "Shown are the courts with the lowest average quarterly clearance ratios."
                )
            else:
                st.info("backlog_clearance_ratio column not found in court_backlog_evolution.parquet.")
        else:
            st.info("Quarter column not detected in court_backlog_evolution.parquet.")
    else:
        st.info("Court quarterly backlog data not available (court_backlog_evolution.parquet).")


# =============================================================================
# Court Performance
# =============================================================================

elif page == "Court Performance":

    section("Court workload and efficiency", "Court-level performance indicators.")

    if performance.empty:
        st.info("Court performance metrics not available.")
    else:
        perf = performance.copy()
        if "jurisdiction_type" in perf.columns and selected_court_types:
            perf = perf[perf["jurisdiction_type"].isin(selected_court_types)]
        perf = perf.loc[perf["resolved_cases"] > 0].copy()
        perf = perf.loc[perf["active_cases"] <= perf["active_cases"].quantile(0.99)]
        perf = perf.loc[perf["mean_duration"] <= perf["mean_duration"].quantile(0.99)]

        top_active = perf.sort_values("active_cases", ascending=False).head(top_n)
        if not top_active.empty:
            x95 = top_active["active_cases"].quantile(0.95)
            fig = px.bar(top_active.sort_values("active_cases"), x="active_cases", y="court_id", orientation="h", color_discrete_sequence=[COLORS["active"]])
            fig = apply_common_layout(fig, height=360, title="Top active courts (by active cases)")
            fig.update_xaxes(title_text="Active cases", range=[0, max(x95 * 1.2, top_active["active_cases"].max())])
            fig.update_yaxes(title_text="Court")
            st.plotly_chart(fig, use_container_width=True)
            st.caption("A small subset of courts concentrates a disproportionately large share of active judicial workload.")

        dur_clean = perf[perf["mean_duration"] > 0]
        if not dur_clean.empty:
            dtop = dur_clean.sort_values("mean_duration", ascending=True).head(top_n)
            y95 = dtop["mean_duration"].quantile(0.95)
            fig = px.bar(dtop, x="mean_duration", y="court_id", orientation="h", color_discrete_sequence=[COLORS["duration"]])
            fig = apply_common_layout(fig, height=360, title="Average case duration by court")
            fig.update_xaxes(title_text="Mean duration (days)", range=[0, max(y95 * 1.2, dtop["mean_duration"].max())])
            st.plotly_chart(fig, use_container_width=True)
            st.caption("Substantial heterogeneity in average duration suggests uneven judicial processing efficiency across courts.")

        size_col = "backlog" if "backlog" in perf.columns else ("resolved_cases" if "resolved_cases" in perf.columns else "active_cases")
        perf_scatter = perf.dropna(subset=["active_cases", "mean_duration"]).copy()
        if not perf_scatter.empty:
            if "efficiency_category" in perf_scatter.columns:
                color_col = "efficiency_category"
            else:
                median_dur = perf_scatter["mean_duration"].median()
                perf_scatter["efficiency_category"] = np.where(perf_scatter["mean_duration"] > median_dur, "High duration", "Low duration")
                color_col = "efficiency_category"
            color_map = {"High duration": COLORS["duration"], "Low duration": COLORS["active"]}
            size_vals  = perf_scatter.get(size_col, perf_scatter["active_cases"]).fillna(0).astype(float)
            size_scaled = np.sqrt(size_vals + 1)
            smin, smax = size_scaled.min(), size_scaled.max()
            size_norm = 6 + (size_scaled - smin) / (smax - smin) * 30 if smax > smin else np.clip(size_scaled, 6, 36)
            perf_scatter["_marker_size"] = size_norm

            fig = px.scatter(perf_scatter, x="active_cases", y="mean_duration", size="_marker_size", size_max=36, color=color_col, color_discrete_map=color_map, hover_data={"court_id": True, "active_cases": True, "mean_duration": True, size_col: True})
            fig.update_traces(marker=dict(opacity=0.65, line=dict(width=0.5, color="rgba(0,0,0,0.15)")))
            median_active = perf_scatter["active_cases"].median()
            median_dur    = perf_scatter["mean_duration"].median()
            xcap = perf_scatter["active_cases"].quantile(0.98) * 1.1
            ycap = perf_scatter["mean_duration"].quantile(0.98) * 1.1
            fig.add_shape(type="line", x0=median_active, x1=median_active, y0=0, y1=ycap, line=dict(dash="dash", color="#666"))
            fig.add_shape(type="line", x0=0, x1=xcap, y0=median_dur, y1=median_dur, line=dict(dash="dash", color="#666"))
            if perf_scatter["active_cases"].max() > 10000:
                fig.update_xaxes(type="log")
            fig = apply_common_layout(fig, height=420, title="Court workload vs resolution duration")
            fig.update_xaxes(title_text="Active cases")
            fig.update_yaxes(title_text="Mean duration (days)")
            try:
                labels = pd.concat([perf_scatter.nlargest(3, size_col), perf_scatter.nlargest(3, "mean_duration")]).drop_duplicates()
                for _, r in labels.iterrows():
                    fig.add_annotation(x=r["active_cases"], y=r["mean_duration"], text=r.get("court_id", ""), showarrow=True, ax=10, ay=-10, font=dict(size=10))
            except Exception:
                pass
            st.plotly_chart(fig, use_container_width=True)
            st.caption("Courts combining high workload and long average durations may indicate localized congestion or limited resolution capacity.")

        st.subheader("Court performance table")
        display_cols = [c for c in ["court_id", "active_cases", "resolved_cases", "mean_duration", "median_duration", "backlog"] if c in perf.columns]
        st.dataframe(perf[display_cols], use_container_width=True)


# =============================================================================
# Duration Analysis
# =============================================================================

elif page == "Duration Analysis":

    section("Case duration analysis", "Distributional analysis of judicial resolution times under right-censoring.")

    if case_metrics.empty:
        st.info("Case-level metrics not available.")
    else:
        cm = case_metrics.copy()
        cm = cm[cm["duration_days"].notna()]
        cm["log_duration"] = np.log1p(cm["duration_days"].clip(lower=0))

        median_log = cm["log_duration"].median()
        fig = px.histogram(cm, x="log_duration", nbins=30, color_discrete_sequence=[COLORS["duration"]], title="Log-transformed distribution of durations (log1p)")
        fig = apply_common_layout(fig, height=360)
        fig.update_layout(showlegend=False)
        fig.update_xaxes(title_text="log1p(duration_days)")
        fig.add_shape(type="line", x0=median_log, x1=median_log, y0=0, y1=1, yref="paper", line=dict(dash="dash", color="#444"))
        fig.add_annotation(x=median_log, y=0.98, yref="paper", text="median", showarrow=False, font=dict(size=10))
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Right-censoring likely biases recent duration estimates downward.")

        ecdf_df = cm.sort_values("log_duration")["log_duration"].reset_index(drop=True)
        ecdf = pd.DataFrame({"x": ecdf_df, "ecdf": (np.arange(len(ecdf_df)) + 1) / len(ecdf_df)})
        fig = px.line(ecdf, x="x", y="ecdf", title="Cumulative distribution of case durations", color_discrete_sequence=[COLORS["duration"]])
        fig = apply_common_layout(fig, height=320)
        fig.update_layout(showlegend=False)
        fig.update_xaxes(title_text="log1p(duration_days)")
        fig.update_yaxes(title_text="Fraction ≤ x")
        st.plotly_chart(fig, use_container_width=True)

        fig = go.Figure()
        fig.add_trace(go.Box(y=cm["log_duration"], boxpoints=False, marker=dict(color=COLORS["duration"]), name="log_duration"))
        fig = apply_common_layout(fig, height=220)
        fig.update_yaxes(range=[0, 8])
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Recent unresolved cases may bias observed duration estimates downward.")

        try:
            from lifelines import KaplanMeierFitter
            st.subheader("Kaplan–Meier survival estimate (termination)")
            if "is_active" in cm.columns:
                durations      = cm["duration_days"].clip(lower=0)
                event_observed = (~cm["is_active"]).astype(int)
                kmf = KaplanMeierFitter()
                kmf.fit(durations, event_observed=event_observed, label="All cases")
                km_df = kmf.survival_function_.reset_index()
                fig = px.line(km_df, x=km_df.columns[0], y=km_df.columns[1], title="Kaplan-Meier survival curve")
                fig = apply_common_layout(fig, height=420)
                fig.update_xaxes(title_text="Duration days")
                fig.update_yaxes(title_text="Survival probability")
                st.plotly_chart(fig, use_container_width=True)
                st.caption("Survival curve: probability a case remains unresolved beyond t days.")
            else:
                st.info("Kaplan–Meier requires `is_active` column in case metrics.")
        except Exception:
            st.caption("Survival-analysis estimates are currently unavailable in this environment.")


# =============================================================================
# Raw Tables
# =============================================================================

elif page == "Raw Tables":

    section("Raw analytical tables", "Direct access to Gold layer outputs.")

    table_choice = st.selectbox(
        "Choose table",
        ["backlog", "clearance", "court_performance", "case_metrics",
         "backlog_quarterly", "clearance_quarterly", "court_backlog_quarterly",
         "duration_circuit_quarterly", "circuit_metrics"],
    )

    table_map = {
        "backlog":                   backlog,
        "clearance":                 clearance,
        "court_performance":         performance,
        "case_metrics":              case_metrics,
        "backlog_quarterly":         backlog_q,
        "clearance_quarterly":       clearance_q,
        "court_backlog_quarterly":   court_backlog_q,
        "duration_circuit_quarterly":duration_circ_q,
        "circuit_metrics":           circuit_metrics,
    }

    df = table_map.get(table_choice, pd.DataFrame()).copy()

    if df.empty:
        st.info("Selected table is empty or not available.")
    else:
        q = st.text_input("Filter (text search across string columns)")
        if q:
            mask = pd.Series(False, index=df.index)
            for c in df.select_dtypes(include=[object]).columns:
                mask = mask | df[c].astype(str).str.contains(q, case=False, na=False)
            df = df.loc[mask]
        st.write(f"Rows: {len(df):,}")
        csv = df.to_csv(index=False)
        st.download_button(label="Download CSV", data=csv, file_name=f"{table_choice}.csv", mime="text/csv")
        st.dataframe(df, use_container_width=True)


# =============================================================================
# Footer
# =============================================================================

st.divider()

with st.expander("Methodology & analytical pipeline"):
    st.markdown(
        """
### Medallion analytical pipeline

This dashboard is built on a layered Medallion architecture:

- **Bronze layer** → raw judicial records incrementally ingested from source systems,
- **Silver layer** → cleaned, standardised, and validated judicial data,
- **Gold layer** → aggregated analytical indicators used for backlog, duration, and court-performance analytics.

### New features in this version

- **Circuit Maps** → geographic bubble maps and an animated quarter-by-quarter backlog map across the 13 US federal circuits; includes a normalised radar chart for multi-metric circuit comparison.
- **Quarterly Analysis** → backlog evolution, inflow/outflow balance, clearance rate, duration trends, and active caseload — all at quarter resolution, broken down by circuit and by court.

### Methodological notes

- Many recent cases remain unresolved (right-censoring).
- Historical resolution records are incomplete for some years.
- Duration statistics primarily reflect resolved cases.
- Clearance indicators may be unstable during sparse-resolution periods.

The dashboard is intended as an analytical observatory of judicial workload dynamics.
"""
    )
    ck_info = load_checkpoint_info()
    layer_sizes = get_layer_sizes()
    st.caption(f"Latest checkpoint: {ck_info.get('dockets', ck_info)}")
    st.caption(
        f"Bronze files: {layer_sizes['bronze']['files']} | "
        f"Silver files: {layer_sizes['silver']['files']} | "
        f"Gold files: {layer_sizes['gold']['files']}"
    )