"""
Circuit Quarterly Dashboard
============================
Focused on circuit × year-quarter analytics:
  - Animated maps: clearance_efficiency, backlog_clearance_ratio, total_backlog by circuit × quarter
  - Total active cases map and breakdown
  - Clearance efficiency heatmap across circuits and quarters
  - Backlog clearance ratio trends and distributions
  - Active caseload decomposition

"""

from pathlib import Path
import os
import json

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import matplotlib.colors as mcolors

# =============================================================================
# Page config & Custom Styling
# =============================================================================

st.set_page_config(
    page_title="Circuit Quarterly Dashboard",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for UI enhancements
st.markdown(
    """
    <style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1e3a8a;
        margin-bottom: 0.1rem;
    }
    .main-subtitle {
        font-size: 1.05rem;
        color: #4b5563;
        margin-bottom: 1.5rem;
    }
    .section-header {
        color: #1e3a8a;
        font-weight: 600;
        margin-top: 1rem;
    }
    .metric-card-container {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 0.5rem;
        padding: 1rem;
        margin-bottom: 1rem;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# =============================================================================
# Paths
# =============================================================================

BASE_DIR = Path(__file__).resolve().parent
GOLD_DIR = BASE_DIR / "gold" / "metrics"


# =============================================================================
# Color semantics & Adjusted Centroids (to avoid overlapping labels)
# =============================================================================

COLORS = {
    "backlog":    "#ff7f0e",
    "active":     "#1f77b4",
    "resolved":   "#2ca02c",
    "duration":   "#9467bd",
    "warning":    "#ffbf00",
    "clearance":  "#d62728",
    "inflow":     "#1f77b4",
    "outflow":    "#2ca02c",
    "efficiency": "#17becf",
}

# Adjusted US Federal Circuit centroids to completely avoid text overlaps
CIRCUIT_CENTROIDS = {
    "1":   {"lat": 44.50,  "lon": -69.00,  "label": "1st Circuit",  "states": "ME, MA, NH, RI, PR"},
    "2":   {"lat": 42.80,  "lon": -74.00,  "label": "2nd Circuit",  "states": "CT, NY, VT"},
    "3":   {"lat": 41.20,  "lon": -77.20,  "label": "3rd Circuit",  "states": "DE, NJ, PA, VI"},
    "4":   {"lat": 37.60,  "lon": -79.00,  "label": "4th Circuit",  "states": "MD, NC, SC, VA, WV"},
    "5":   {"lat": 31.00,  "lon": -100.0,  "label": "5th Circuit",  "states": "LA, MS, TX"},
    "6":   {"lat": 39.50,  "lon": -85.00,  "label": "6th Circuit",  "states": "KY, MI, OH, TN"},
    "7":   {"lat": 42.00,  "lon": -89.00,  "label": "7th Circuit",  "states": "IL, IN, WI"},
    "8":   {"lat": 44.00,  "lon": -98.00,  "label": "8th Circuit",  "states": "AR, IA, MN, MO, NE, ND, SD"},
    "9":   {"lat": 41.00,  "lon": -119.5,  "label": "9th Circuit",  "states": "AK, AZ, CA, HI, ID, MT, NV, OR, WA"},
    "10":  {"lat": 39.00,  "lon": -106.0,  "label": "10th Circuit", "states": "CO, KS, NM, OK, UT, WY"},
    "11":  {"lat": 31.50,  "lon": -84.00,  "label": "11th Circuit", "states": "AL, FL, GA"},
    "dc":  {"lat": 38.90,  "lon": -74.50,  "label": "DC Circuit",   "states": "DC"},      # Placed east into Atlantic
    "fc":  {"lat": 36.80,  "lon": -73.50,  "label": "Fed. Circuit", "states": "National"}, # Placed further southeast in Atlantic
}


# State abbreviation → circuit key
STATE_TO_CIRCUIT: dict[str, str] = {
    "ME": "1", "MA": "1", "NH": "1", "RI": "1",
    "CT": "2", "NY": "2", "VT": "2",
    "DE": "3", "NJ": "3", "PA": "3",
    "MD": "4", "NC": "4", "SC": "4", "VA": "4", "WV": "4",
    "LA": "5", "MS": "5", "TX": "5",
    "KY": "6", "MI": "6", "OH": "6", "TN": "6",
    "IL": "7", "IN": "7", "WI": "7",
    "AR": "8", "IA": "8", "MN": "8", "MO": "8", "NE": "8", "ND": "8", "SD": "8",
    "AK": "9", "AZ": "9", "CA": "9", "HI": "9", "ID": "9",
    "MT": "9", "NV": "9", "OR": "9", "WA": "9",
    "CO": "10", "KS": "10", "NM": "10", "OK": "10", "UT": "10", "WY": "10",
    "AL": "11", "FL": "11", "GA": "11",
    "DC": "dc",
}

CIRCUIT_COLORS: dict[str, str] = {
    "1":  "#4e79a7",
    "2":  "#f28e2b",
    "3":  "#e15759",
    "4":  "#76b7b2",
    "5":  "#59a14f",
    "6":  "#edc948",
    "7":  "#b07aa1",
    "8":  "#ff9da7",
    "9":  "#9c755f",
    "10": "#bab0ac",
    "11": "#d37295",
    "dc": "#fabfd2",
    "fc": "#8cd17d",
}


def _norm_circuit(c: str) -> str:
    c = str(c).strip().lower()
    for key in sorted(CIRCUIT_CENTROIDS.keys(), key=len, reverse=True):
        if c == key or c == f"ca{key}" or c.endswith(key):
            return key
    return c


# =============================================================================
# Layout helpers
# =============================================================================


def apply_common_layout(fig: go.Figure, height: int = 420, title: str | None = None) -> go.Figure:
    layout_args = dict(
        template="plotly_white",
        height=height,
        margin=dict(l=40, r=20, t=50, b=40),
        font=dict(family="Segoe UI, Arial, sans-serif", size=11),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
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
            font=dict(size=14),
        )
    fig.update_layout(**layout_args)
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='#f1f5f9')
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='#f1f5f9')
    return fig


def section(title: str, intro: str | None = None):
    st.divider()
    st.markdown(f"<h2 class='section-header'>{title}</h2>", unsafe_allow_html=True)
    if intro:
        st.markdown(intro)


def safe_parquet(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)


# =============================================================================
# Geo helpers
# =============================================================================


def _enrich_with_geo(df: pd.DataFrame, circuit_col: str = "circuit") -> pd.DataFrame:
    """Attach lat/lon/label to a circuit-level dataframe."""
    if circuit_col not in df.columns:
        return df
    rows = []
    for _, row in df.iterrows():
        key = _norm_circuit(str(row[circuit_col]))
        geo = CIRCUIT_CENTROIDS.get(key, {})
        rows.append({**row.to_dict(), **{
            "lat":           geo.get("lat", np.nan),
            "lon":           geo.get("lon", np.nan),
            "circuit_label": geo.get("label", str(row[circuit_col])),
            "states":        geo.get("states", ""),
        }})
    return pd.DataFrame(rows).dropna(subset=["lat", "lon"])


def _choropleth_geo_layout(fig: go.Figure, title: str, height: int = 520) -> go.Figure:
    fig.update_geos(
        scope="usa",
        showland=True,
        landcolor="#f8fafc",
        showcoastlines=True,
        coastlinecolor="#cbd5e1",
        showsubunits=True,
        subunitcolor="#e2e8f0",
        showlakes=False,
        projection_type="albers usa",
    )
    fig.update_layout(
        title=dict(text=title, x=0.01, font=dict(size=14, family="Segoe UI, Arial")),
        height=height,
        margin=dict(l=10, r=10, t=50, b=10),
        template="plotly_white",
        font=dict(family="Segoe UI, Arial", size=11),
    )
    return fig


def _build_state_choropleth_df(
    circuit_df: pd.DataFrame,
    metric_col: str,
) -> pd.DataFrame:
    records = []
    for _, row in circuit_df.iterrows():
        key = _norm_circuit(str(row["circuit"]))
        for state, c_key in STATE_TO_CIRCUIT.items():
            if c_key == key:
                rec = row.to_dict()
                rec["state"] = state
                rec["circuit_key"] = key
                rec["circuit_label"] = CIRCUIT_CENTROIDS.get(key, {}).get("label", key)
                rec["circuit_color"] = CIRCUIT_COLORS.get(key, "#aaaaaa")
                val = row[metric_col]
                if isinstance(val, pd.Series):
                    val = val.iloc[0]
                rec["metric_value"] = float(val) if metric_col in row.index else np.nan
                records.append(rec)
    df_states = pd.DataFrame(records)
    if df_states.empty:
        return df_states
    v = df_states["metric_value"].fillna(0).clip(lower=0)
    v_max = v.max()
    df_states["metric_norm"] = v / (v_max + 1e-9)
    return df_states


def static_choropleth_map(
    df: pd.DataFrame,
    metric_col: str,
    title: str,
    height: int = 500,
) -> go.Figure:
    state_df = _build_state_choropleth_df(df, metric_col)
    if state_df.empty:
        return go.Figure()

    fig = go.Figure()
    circuits_present = state_df["circuit_key"].unique()
    for key in sorted(circuits_present, key=lambda x: (len(x), x)):
        sub = state_df[state_df["circuit_key"] == key]
        label = CIRCUIT_CENTROIDS.get(key, {}).get("label", key)
        color = CIRCUIT_COLORS.get(key, "#aaaaaa")

        fig.add_trace(go.Choropleth(
            locations=sub["state"],
            z=sub["metric_norm"],
            locationmode="USA-states",
            colorscale=get_formatted_colorscale(color), 
            showscale=False,
            zmin=0, zmax=1,
            marker_line_color="white",
            marker_line_width=1.2,
            name=label,
            customdata=np.stack([
                sub["metric_value"].values,
                sub["circuit_label"].values,
            ], axis=-1),
            hovertemplate=(
                "<b>%{customdata[1]}</b><br>"
                f"{metric_col.replace('_', ' ').title()}: %{{customdata[0]:,.2f}}<br>"
                "State: %{location}<extra></extra>"
            ),
        ))

    # Centroid annotations: show metric value as text on map
    geo = _enrich_with_geo(df)
    if not geo.empty and metric_col in geo.columns:
        v = geo[metric_col].fillna(0).clip(lower=0)
        v_max = v.max()

        marker_sizes = []
        for c in geo["circuit"]:
            key = _norm_circuit(str(c))
            # Keep very small bubbles only for DC and FC
            if key in ["dc", "fc"]:
                marker_sizes.append(6)
            else:
                marker_sizes.append(0)

        fig.add_trace(go.Scattergeo(
            lat=geo["lat"],
            lon=geo["lon"],
            text=geo.apply(
                lambda r: f"{CIRCUIT_CENTROIDS.get(_norm_circuit(str(r['circuit'])), {}).get('label', r['circuit'])}<br>"
                          f"{_fmt_metric(r[metric_col])}",
                axis=1,
            ),
            mode="markers+text",
            textposition="top center",
            textfont=dict(size=10, color="#1e293b", family="Segoe UI, Arial"), 
            marker=dict(
                size=marker_sizes, 
                color=[CIRCUIT_COLORS.get(_norm_circuit(str(c)), "#888") for c in geo["circuit"]],
                line=dict(width=1.0, color="white"),
                opacity=0.9,
            ),
            hovertemplate="<b>%{text}</b><extra></extra>",
            showlegend=False,
            name="",
        ))

    _choropleth_geo_layout(fig, title, height)
    fig.update_layout(
        legend=dict(
            title="Circuit",
            orientation="v",
            x=1.01, y=0.5,
            xanchor="left",
            font=dict(size=9),
            itemsizing="constant",
        ),
        showlegend=True,
    )
    return fig


def get_formatted_colorscale(base_color):
    rgb = mcolors.to_rgb(base_color)
    c1 = f"rgba({rgb[0]*255:.0f}, {rgb[1]*255:.0f}, {rgb[2]*255:.0f}, 0.20)"
    c2 = f"rgba({rgb[0]*255:.0f}, {rgb[1]*255:.0f}, {rgb[2]*255:.0f}, 0.90)"
    return [[0, c1], [1, c2]]


def animated_choropleth_map(
    df: pd.DataFrame,
    metric_col: str,
    quarter_col: str,
    title: str,
    height: int = 540,
    hover_extras: list[str] | None = None,
    colorscale: str = "Oranges",
) -> go.Figure:
    if df.empty or metric_col not in df.columns:
        return go.Figure()

    quarters = sorted(df[quarter_col].dropna().unique())
    if not quarters:
        return go.Figure()

    frames_data = []
    for q in quarters:
        q_df = df[df[quarter_col] == q].copy()
        state_df = _build_state_choropleth_df(q_df, metric_col)
        if not state_df.empty:
            state_df[quarter_col] = q
            frames_data.append(state_df)

    if not frames_data:
        return go.Figure()

    all_states = pd.concat(frames_data, ignore_index=True)
    fig = go.Figure()

    global_zmin = float(all_states["metric_value"].min())
    global_zmax = float(all_states["metric_value"].max())
    if global_zmin == global_zmax:
        global_zmax += 1e-9

    def _make_circuit_traces(q: str) -> list[go.Trace]:
        sub_all = all_states[all_states[quarter_col] == q]
        traces: list[go.BaseTraceType] = []

        if sub_all.empty:
            return traces

        traces.append(go.Choropleth(
            locations=sub_all["state"],
            z=sub_all["metric_value"],
            locationmode="USA-states",
            colorscale=colorscale,
            showscale=True,
            zmin=global_zmin,
            zmax=global_zmax,
            marker_line_color="white",
            marker_line_width=1.2,
            colorbar=dict(
                title=metric_col.replace('_', ' ').title(),
                thickness=15,
                len=0.7,
                yanchor="middle",
                y=0.5,
                xanchor="left",
                x=1.02
            ),
            customdata=np.stack([
                sub_all["metric_value"].values,
                sub_all["circuit_label"].values,
            ], axis=-1),
            hovertemplate=(
                "<b>%{customdata[1]}</b><br>"
                f"{metric_col.replace('_', ' ').title()}: %{{customdata[0]:,.2f}}<br>"
                "State: %{location}<extra></extra>"
            ),
        ))

        # Centroid annotations: Bubble logic implemented here
        geo = _enrich_with_geo(df[df[quarter_col] == q])
        if not geo.empty and metric_col in geo.columns:
            extras = hover_extras or []
            extra_text = geo.apply(
                lambda r: "".join(
                    f"<br>{e}: {_fmt_metric(r[e])}" for e in extras if e in r.index
                ),
                axis=1,
            )

            # Bubble size constraints: DC and FC get very small markers, others get zero
            marker_sizes = []
            for c in geo["circuit"]:
                key = _norm_circuit(str(c))
                if key in ["dc", "fc"]:
                    marker_sizes.append(6)
                else:
                    marker_sizes.append(0)

            traces.append(go.Scattergeo(
                lat=geo["lat"],
                lon=geo["lon"],
                text=geo.apply(
                    lambda r: (
                        f"{CIRCUIT_CENTROIDS.get(_norm_circuit(str(r['circuit'])), {}).get('label', r['circuit'])}<br>"
                        f"{_fmt_metric(r[metric_col])}"
                    ),
                    axis=1,
                ),
                mode="markers+text",
                textposition="top center",
                textfont=dict(size=10, color="#1e293b", family="Segoe UI, Arial"), 
                marker=dict(
                    size=marker_sizes, 
                    color=geo[metric_col].fillna(0),
                    colorscale=colorscale,
                    cmin=global_zmin,
                    cmax=global_zmax,
                    line=dict(width=1.0, color="#334155"),
                    opacity=1.0,
                ),
                showlegend=False,
                name="",
                customdata=np.stack([
                    geo[metric_col].fillna(0).values,
                    extra_text.values,
                ], axis=-1),
                hovertemplate=(
                    "<b>%{text}</b>"
                    "%{customdata[1]}"
                    "<extra></extra>"
                ),
            ))
        return traces

    for t in _make_circuit_traces(quarters[0]):
        fig.add_trace(t)

    fig.frames = [
        go.Frame(
            data=_make_circuit_traces(q),
            name=str(q),
            layout=go.Layout(title_text=f"{title} — {q}"),
        )
        for q in quarters
    ]

    fig.update_layout(
        updatemenus=[dict(
            type="buttons",
            showactive=False,
            y=0,
            x=0.5,
            xanchor="center",
            yanchor="top",
            pad=dict(t=10, b=0),
            buttons=[
                dict(label="▶ Play",  method="animate",
                     args=[None, dict(frame=dict(duration=600, redraw=True),
                                      fromcurrent=True, mode="immediate")]),
                dict(label="⏸ Pause", method="animate",
                     args=[[None], dict(frame=dict(duration=0, redraw=False),
                                        mode="immediate")]),
            ],
        )],
        sliders=[dict(
            active=0,
            currentvalue=dict(prefix="Quarter: ", font=dict(size=12)),
            pad=dict(t=50, b=10),
            steps=[
                dict(
                    method="animate",
                    label=str(q),
                    args=[[str(q)], dict(frame=dict(duration=600, redraw=True),
                                         mode="immediate")],
                )
                for q in quarters
            ],
        )],
    )

    _choropleth_geo_layout(fig, f"{title} — {quarters[0]}", height)
    fig.update_layout(
        margin=dict(l=5, r=5, t=60, b=80),
        showlegend=False,
    )
    return fig


def _fmt_metric(v) -> str:
    try:
        f = float(v)
        if abs(f) >= 1_000_000:
            return f"{f/1_000_000:.1f}M"
        if abs(f) >= 1_000:
            return f"{f/1_000:.1f}k"
        return f"{f:.2f}"
    except Exception:
        return str(v)


# =============================================================================
# Data loaders
# =============================================================================


@st.cache_data
def load_circuit_backlog_quarterly() -> pd.DataFrame:
    candidates = [
        GOLD_DIR / "backlog_evolution_circuit_by_quarter.parquet",
        #GOLD_DIR / "backlog_evolution_circuit_by_circuit_quarter.parquet",
    ]
    for p in candidates:
        if p.exists():
            return pd.read_parquet(p)
    return pd.DataFrame()


@st.cache_data
def load_clearance_circuit_quarterly() -> pd.DataFrame:
    candidates = [
        GOLD_DIR / "backlog_evolution_circuit_by_quarter.parquet",
        #GOLD_DIR / "clearance_rate_by_quarter.parquet",
    ]
    for p in candidates:
        if p.exists():
            df = pd.read_parquet(p)
            if "circuit" in df.columns:
                return df
    return pd.DataFrame()


@st.cache_data
def load_active_circuit_quarterly() -> pd.DataFrame:
    p = GOLD_DIR / "active_cases_by_circuit_quarter.parquet"
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()


@st.cache_data
def load_active_circuit_static() -> pd.DataFrame:
    candidates = [
        #GOLD_DIR / "circuit_performance_metrics.parquet",
        GOLD_DIR / "metrics_by_circuit.parquet",
    ]
    for p in candidates:
        if p.exists():
            return pd.read_parquet(p)
    return pd.DataFrame()


@st.cache_data
def load_court_backlog_evolution() -> pd.DataFrame:
    p = GOLD_DIR / "court_backlog_evolution.parquet"
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()

@st.cache_data
def load_jurisdiction_backlog_evolution() -> pd.DataFrame:
    p = GOLD_DIR / "jurisdiction_backlog_evolution.parquet"
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()

# =============================================================================
# Load data
# =============================================================================

backlog_cq    = load_circuit_backlog_quarterly()
clearance_cq  = load_clearance_circuit_quarterly()
active_cq     = load_active_circuit_quarterly()
circuit_snap  = load_active_circuit_static()
court_backlog = load_court_backlog_evolution()
jurisdiction_backlog = load_jurisdiction_backlog_evolution()

# =============================================================================
# Sidebar Layout
# =============================================================================

st.sidebar.markdown("<h2 style='color:#1e3a8a;'>⚖️ Control panel</h2>", unsafe_allow_html=True)

page = st.sidebar.radio(
    "Navigation menu",
    [
        "Maps — Animated",
        "Maps — Snapshot",
        "Backlog & Clearance Trends",
        "Court Backlog Evolution",
        "Active Cases",
        "Jurisdiction Metrics",
        "Raw Tables",
    ],
)

_all_circuits: list[str] = []
for _df in [backlog_cq, clearance_cq, active_cq, circuit_snap, court_backlog]:
    if not _df.empty and "circuit" in _df.columns:
        _all_circuits += [str(c) for c in _df["circuit"].dropna().unique()]
all_circuits = sorted(set(_all_circuits))

selected_circuits = st.sidebar.multiselect(
    "Filter circuits", options=all_circuits, default=all_circuits
)

_qcol_main = "year_quarter"
_quarters: list[str] = []
for _df, _col in [
    (backlog_cq,    "year_quarter"),
    (clearance_cq,  next((c for c in clearance_cq.columns if "quarter" in c.lower()), "")),
    (active_cq,     next((c for c in active_cq.columns    if "quarter" in c.lower()), "")),
    (court_backlog, "year_quarter"),
]:
    if not _df.empty and _col and _col in _df.columns:
        _quarters += [str(q) for q in _df[_col].dropna().unique()]
all_quarters = sorted(q for q in set(_quarters) if q >= "2023-q1")


if len(all_quarters) >= 2:
    q_range = st.sidebar.select_slider(
        "Quarter range selection", options=all_quarters, value=(all_quarters[0], all_quarters[-1])
    )
else:
    q_range = (all_quarters[0], all_quarters[-1]) if len(all_quarters) == 2 else (None, None)


def _fq(df: pd.DataFrame, col: str) -> pd.DataFrame:
    if q_range[0] is None or col not in df.columns:
        return df
    return df[df[col].between(q_range[0], q_range[1])].copy()


def _fc(df: pd.DataFrame) -> pd.DataFrame:
    if "circuit" in df.columns and selected_circuits:
        return df[df["circuit"].astype(str).isin(selected_circuits)].copy()
    return df


# =============================================================================
# Main Header
# =============================================================================

st.markdown("<div class='main-title'>Circuit Quarterly Dashboard</div>", unsafe_allow_html=True)
st.markdown("<div class='main-subtitle'>Federal Court Analytics Portal — Backlog accumulation, clearance rates, and quarterly volume indicators</div>", unsafe_allow_html=True)


# =============================================================================
# PAGE: Maps — Animated
# =============================================================================

if page == "Maps — Animated":

    section(
        "Animated circuit maps by quarter",
        "Each frame represents one year-quarter. Use the play button or scrub the slider "
        "to watch metrics evolve across the 13 US federal circuits.",
    )

    anim_options: dict[str, dict] = {}

    if not backlog_cq.empty:
        if "backlog" in backlog_cq.columns:
            anim_options["Total backlog"] = {
                "df": backlog_cq, "size": "backlog", "color": "backlog",
                "qcol": "year_quarter", "scale": "Oranges",
                "extras": ["inflow", "outflow", "net_change"],
            }
        if "clearance_efficiency" in backlog_cq.columns:
            anim_options["Clearance efficiency"] = {
                "df": backlog_cq, "size": "clearance_efficiency", "color": "clearance_efficiency",
                "qcol": "year_quarter", "scale": "RdYlGn",
                "extras": ["inflow", "outflow", "backlog"],
            }
        if "backlog_clearance_ratio" in backlog_cq.columns:
            anim_options["Backlog clearance ratio"] = {
                "df": backlog_cq, "size": "backlog_clearance_ratio", "color": "backlog_clearance_ratio",
                "qcol": "year_quarter", "scale": "RdBu",
                "extras": ["inflow", "outflow", "backlog"],
            }
    if not active_cq.empty:
        _aq_col = next((c for c in active_cq.columns if "count" in c.lower() or c == "active_cases_count"), None)
        if _aq_col:
            _aq = active_cq.rename(columns={
                next((c for c in active_cq.columns if "quarter" in c.lower()), _aq_col): "year_quarter",
                _aq_col: "active_cases",
            })
            anim_options["Active cases"] = {
                "df": _aq, "size": "active_cases", "color": "active_cases",
                "qcol": "year_quarter", "scale": "Blues",
                "extras": [],
            }

    if not anim_options:
        st.info(
            "No animated map data available. Ensure circuit_backlog_evolution.parquet "
            "or active_cases_by_circuit_quarter.parquet is present in gold/metrics/."
        )
    else:
        metric_name = st.selectbox("Select metric to animate", list(anim_options.keys()))
        cfg = anim_options[metric_name]

        df_anim = _fq(_fc(cfg["df"]), cfg["qcol"])
        if cfg["size"] in df_anim.columns:
            df_anim[cfg["size"]] = df_anim[cfg["size"]].clip(lower=0)

        if df_anim.empty:
            st.info("No data available for the selected circuits or quarters.")
        else:
            fig_anim = animated_choropleth_map(
                df=df_anim,
                metric_col=cfg["color"],
                quarter_col=cfg["qcol"],
                title=f"{metric_name} across US federal circuits",
                hover_extras=[c for c in cfg["extras"] if c in df_anim.columns],
                colorscale=cfg.get("scale", "Oranges"),
            )
            st.plotly_chart(fig_anim, use_container_width=True)
            

        if not df_anim.empty and cfg["qcol"] in df_anim.columns:
            latest_q = df_anim[cfg["qcol"]].max()
            st.subheader(f"Latest quarter snapshot — {latest_q}")
            show_cols = ["circuit"] + [
                c for c in [cfg["color"]] + cfg["extras"] if c in df_anim.columns
            ]
            snap = df_anim[df_anim[cfg["qcol"]] == latest_q][show_cols].sort_values(
                cfg["color"], ascending=False
            )
            st.dataframe(snap.reset_index(drop=True), use_container_width=True)


# =============================================================================
# PAGE: Maps — Snapshot
# =============================================================================

elif page == "Maps — Snapshot":

    section(
        "Circuit snapshot map",
        "Single-quarter choropleth representation. Choose a quarter to display a static "
        "snapshot of any circuit-level metric.",
    )

    if backlog_cq.empty and circuit_snap.empty:
        st.info("No circuit-level data available for snapshot rendering.")
    else:
        snap_quarters = all_quarters or []
        if snap_quarters:
            snap_q = st.selectbox("Select historical quarter", options=snap_quarters[::-1], index=0)
        else:
            snap_q = None

        _snap_df = backlog_cq if not backlog_cq.empty else pd.DataFrame()
        snap_metric_options = [
            c for c in ["backlog", "clearance_efficiency", "backlog_clearance_ratio",
                        "inflow", "outflow", "active_cases", "net_change"]
            if not _snap_df.empty and c in _snap_df.columns
        ]
        if not snap_metric_options and not circuit_snap.empty:
            snap_metric_options = [
                c for c in ["active_cases_count", "active_cases", "avg_resolution_days"]
                if c in circuit_snap.columns
            ]
            _snap_df = circuit_snap

        if not snap_metric_options:
            st.info("No suitable numeric metrics found for map snapshot rendering.")
        else:
            snap_metric = st.selectbox("Select metric indicator", options=snap_metric_options)

            if "year_quarter" in _snap_df.columns and snap_q:
                snap_data = _snap_df[_snap_df["year_quarter"] == snap_q].copy()
            else:
                snap_data = _snap_df.copy()

            snap_data = _fc(snap_data)

            if snap_data.empty or snap_metric not in snap_data.columns:
                st.info("No data matching the selection criteria.")
            else:
                snap_data[snap_metric] = snap_data[snap_metric].clip(lower=0)
                fig_snap = static_choropleth_map(
                    df=snap_data,
                    metric_col=snap_metric,
                    title=f"{snap_metric.replace('_', ' ').title()} by circuit"
                          + (f" — {snap_q}" if snap_q else ""),
                )
                st.plotly_chart(fig_snap, use_container_width=True)

                bar_df = snap_data.dropna(subset=[snap_metric]).sort_values(snap_metric, ascending=False)
                bar_color_map = {str(c): CIRCUIT_COLORS.get(_norm_circuit(str(c)), "#aaaaaa") for c in bar_df["circuit"].unique()}
                bar_df["circuit_str"] = bar_df["circuit"].astype(str)

                fig_bar = px.bar(
                    bar_df,
                    x="circuit_str",
                    y=snap_metric,
                    color="circuit_str",
                    color_discrete_map=bar_color_map,
                    labels={"circuit_str": "Circuit", snap_metric: snap_metric.replace("_", " ").title()},
                )
                fig_bar = apply_common_layout(
                    fig_bar, height=360,
                    title=f"{snap_metric.replace('_', ' ').title()} — circuit ranking"
                )
                fig_bar.update_layout(showlegend=False)
                st.plotly_chart(fig_bar, use_container_width=True)


# =============================================================================
# PAGE: Backlog & Clearance Trends
# =============================================================================

elif page == "Backlog & Clearance Trends":

    section(
        "Backlog and clearance analytics — circuit × quarter",
        "Quarterly time-series of backlog accumulation, clearance ratio, and clearance efficiency "
        "broken down by circuit.",
    )

    st.subheader("Backlog evolution by circuit")

    if not backlog_cq.empty and "backlog" in backlog_cq.columns:
        bq = _fq(_fc(backlog_cq), "year_quarter")
        if not bq.empty:
            fig = px.line(
                bq, x="year_quarter", y="backlog", color="circuit",
                markers=True,
                color_discrete_sequence=px.colors.qualitative.Set2,
                labels={"year_quarter": "Quarter", "backlog": "Backlog (cumulative cases)"},
            )
            fig = apply_common_layout(fig, height=420, title="Cumulative backlog by circuit and quarter")
            fig.update_xaxes(tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)

            fig_area = px.area(
                bq.sort_values("year_quarter"),
                x="year_quarter", y="backlog", color="circuit",
                color_discrete_sequence=px.colors.qualitative.Set2,
                labels={"year_quarter": "Quarter", "backlog": "Backlog"},
            )
            fig_area = apply_common_layout(
                fig_area, height=360,
                title="System-wide backlog composition by circuit (stacked area)"
            )
            fig_area.update_xaxes(tickangle=-45)
            st.plotly_chart(fig_area, use_container_width=True)
        else:
            st.info("No backlog data matching selected filters.")
    else:
        st.info("Circuit backlog evolution data not available.")

    st.subheader("Backlog clearance ratio by circuit")
    st.markdown(
        "_Clearance ratio = outflow / inflow. Values < 1 mean more cases filed than resolved "
        "in the quarter, adding to the backlog._"
    )

    _bcr_df = pd.DataFrame()
    if not backlog_cq.empty and "backlog_clearance_ratio" in backlog_cq.columns:
        _bcr_df = backlog_cq
    elif not clearance_cq.empty and "backlog_clearance_rate" in clearance_cq.columns:
        _bcr_df = clearance_cq.rename(columns={"backlog_clearance_rate": "backlog_clearance_ratio"})

    if not _bcr_df.empty:
        bcr_col = "backlog_clearance_ratio" if "backlog_clearance_ratio" in _bcr_df.columns else "backlog_clearance_rate"
        qcol_bcr = "year_quarter" if "year_quarter" in _bcr_df.columns else next(
            (c for c in _bcr_df.columns if "quarter" in c.lower()), None
        )
        if qcol_bcr:
            bcr = _fq(_fc(_bcr_df), qcol_bcr)
            if not bcr.empty:
                fig = px.line(
                    bcr, x=qcol_bcr, y=bcr_col, color="circuit",
                    markers=True,
                    color_discrete_sequence=px.colors.qualitative.Set2,
                    labels={qcol_bcr: "Quarter", bcr_col: "Clearance ratio (outflow / inflow)"},
                )
                fig.add_hline(y=1.0, line_dash="dash", line_color="#666", annotation_text="equilibrium (1.0)")
                fig = apply_common_layout(fig, height=420, title="Quarterly backlog clearance ratio by circuit")
                fig.update_yaxes(range=[0, max(3.0, float(bcr[bcr_col].quantile(0.98)) * 1.1)])
                fig.update_xaxes(tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)

                fig_box = px.box(
                    bcr.dropna(subset=[bcr_col]),
                    x="circuit", y=bcr_col,
                    color="circuit",
                    color_discrete_sequence=px.colors.qualitative.Set2,
                    labels={"circuit": "Circuit", bcr_col: "Clearance ratio"},
                    title="Distribution of quarterly clearance ratios by circuit",
                )
                fig_box.add_hline(y=1.0, line_dash="dash", line_color="#666")
                fig_box = apply_common_layout(fig_box, height=380)
                fig_box.update_yaxes(range=[0, 4])
                st.plotly_chart(fig_box, use_container_width=True)
            else:
                st.info("No clearance ratio data matches selected filters.")
    else:
        st.info("Backlog clearance ratio data not available.")


# =============================================================================
# PAGE: Court Backlog Evolution
# =============================================================================

elif page == "Court Backlog Evolution":

    section(
        "Court-level backlog evolution",
        "Granular analytics and historical processing trajectories mapped directly to individual courts.",
    )

    if court_backlog.empty:
        st.info(
            "Court backlog evolution data not available. Ensure court_backlog_evolution.parquet "
            "is present in gold/metrics/."
        )
    else:
        # Robust check to correctly grab the active "court_id" or other valid descriptors
        court_col = None
        for col in ["court_id", "court_name", "court"]:
            if col in court_backlog.columns:
                court_col = col
                break
        
        if not court_col:
            st.warning("No standard court identifier column (court_id, court_name, court) found in the dataset.")
        else:
            # Apply layout filter configurations dynamically
            cb_filtered = _fq(_fc(court_backlog), "year_quarter")
            
            # Fall back to unfiltered court_backlog list if restrictive selections render cb_filtered empty
            available_cb = cb_filtered if not cb_filtered.empty else court_backlog
            all_courts = sorted(available_cb[court_col].dropna().unique())
            
            if not all_courts:
                all_courts = sorted(court_backlog[court_col].dropna().unique())
                available_cb = court_backlog

            selected_courts = st.multiselect(
                "🔍 Select courts to analyze:",
                options=all_courts,
                default=all_courts[:1] if all_courts else [],
                help="Type to search and select specific courts. You can select multiple."
            )

            if not selected_courts:
                st.info("Please select at least one court from the dropdown menu to display statistics.")
            else:
                for idx, court_name in enumerate(selected_courts):
                    # Filter data for this court
                    court_df = available_cb[available_cb[court_col] == court_name].sort_values("year_quarter")
                    
                    if court_df.empty:
                        # Fallback to general file if needed
                        court_df = court_backlog[court_backlog[court_col] == court_name].sort_values("year_quarter")
                    
                    if court_df.empty:
                        st.markdown(f"### 🏛️ {court_name} — No data available")
                        continue
                    
                    # Compute latest quarter specs
                    latest_q = court_df["year_quarter"].max()
                    latest_data = court_df[court_df["year_quarter"] == latest_q].iloc[0]
                    
                    st.markdown(f"### 🏛️ {court_name}")
                    
                    # Prettified metrics blocks
                    cols = st.columns(5)
                    
                    with cols[0]:
                        st.markdown("<div class='metric-card-container'>", unsafe_allow_html=True)
                        st.metric(label="Latest Data Quarter", value=str(latest_q))
                        st.markdown("</div>", unsafe_allow_html=True)
                        
                    with cols[1]:
                        st.markdown("<div class='metric-card-container'>", unsafe_allow_html=True)
                        backlog_val = int(latest_data['total_backlog']) if "total_backlog" in latest_data and not pd.isna(latest_data['total_backlog']) else "N/A"
                        st.metric(
                            label="Backlog Cases", 
                            value=f"{backlog_val:,}" if isinstance(backlog_val, int) else backlog_val
                        )
                        st.markdown("</div>", unsafe_allow_html=True)
                        
                    with cols[2]:
                        st.markdown("<div class='metric-card-container'>", unsafe_allow_html=True)
                        inflow_val = int(latest_data['inflow_cases']) if "inflow_cases" in latest_data and not pd.isna(latest_data['inflow_cases']) else "N/A"
                        st.metric(
                            label="Inflow (New Cases)", 
                            value=f"{inflow_val:,}" if isinstance(inflow_val, int) else inflow_val
                        )
                        st.markdown("</div>", unsafe_allow_html=True)
                        
                    with cols[3]:
                        st.markdown("<div class='metric-card-container'>", unsafe_allow_html=True)
                        outflow_val = int(latest_data['outflow_cases']) if "outflow_cases" in latest_data and not pd.isna(latest_data['outflow_cases']) else "N/A"
                        st.metric(
                            label="Outflow (Resolved)", 
                            value=f"{outflow_val:,}" if isinstance(outflow_val, int) else outflow_val
                        )
                        st.markdown("</div>", unsafe_allow_html=True)
                    
                    with cols[4]:
                        st.markdown("<div class='metric-card-container'>", unsafe_allow_html=True)
                        active_val = int(latest_data['active_cases_count']) if "active_cases_count" in latest_data and not pd.isna(latest_data['active_cases_count']) else "N/A"
                        st.metric(
                            label="Still active cases", 
                            value=f"{active_val:,}" if isinstance(active_val, int) else active_val
                        )
                        st.markdown("</div>", unsafe_allow_html=True)
                    
                    # Table view for quarter-by-quarter statistics
                    st.markdown(f"**Historical quarter-by-quarter stats for {court_name}:**")
                    display_cols = ["year_quarter", "active_cases_count","inflow_cases", "outflow_cases", "total_backlog", "clearance_efficiency", "backlog_clearance_ratio"]
                    present_cols = [c for c in display_cols if c in court_df.columns]

                    # Auto-compute net change if not present
                    if "net_change" not in court_df.columns and "inflow" in court_df.columns and "outflow" in court_df.columns:
                        court_df["net_change"] = court_df["inflow"] - court_df["outflow"]
                    if "net_change" in court_df.columns:
                        present_cols.append("net_change")

                    # Display formatted dataframe
                    st.dataframe(
                        court_df[present_cols].reset_index(drop=True),
                        use_container_width=True
                    )
                    
                    if idx < len(selected_courts) - 1:
                        st.divider()



# =============================================================================
# PAGE: Active Cases
# =============================================================================

elif page == "Active Cases":

    section(
        "Active caseload — circuits and quarters",
        "Cases that remain open (filed after 2020 and not yet terminated), "
        "tracked by circuit across quarters.",
    )

    _aq_df = pd.DataFrame()
    _aq_qcol = ""
    _aq_cnt  = ""

    if not active_cq.empty:
        _aq_qcol = next((c for c in active_cq.columns if "quarter" in c.lower()), "")
        _aq_cnt  = next((c for c in active_cq.columns if "count" in c.lower() or c == "active_cases_count"), "")
        if _aq_qcol and _aq_cnt:
            _aq_df = active_cq.rename(columns={_aq_qcol: "year_quarter", _aq_cnt: "active_cases"})
    elif not backlog_cq.empty and "active_cases" in backlog_cq.columns:
        _aq_df   = backlog_cq
        _aq_qcol = "year_quarter"
        _aq_cnt  = "active_cases"

    if not _aq_df.empty:
        aq = _fq(_fc(_aq_df), "year_quarter")
        aq = aq[aq["year_quarter"].astype(str) >= "2023-Q1"]

        if not aq.empty:
            aq_color_map = {str(c): CIRCUIT_COLORS.get(_norm_circuit(str(c)), "#aaaaaa") for c in aq["circuit"].unique()}

            fig_area = px.area(
                aq.sort_values("year_quarter"),
                x="year_quarter", y="active_cases", color="circuit",
                color_discrete_map=aq_color_map,
                labels={"year_quarter": "Quarter", "active_cases": "Active cases"},
            )
            fig_area = apply_common_layout(
                fig_area, height=400,
                title="Active caseload by circuit (stacked area)"
            )
            fig_area.update_xaxes(tickangle=-45, range=["2023-Q1", None])
            st.plotly_chart(fig_area, use_container_width=True)

            fig_line = px.line(
                aq, x="year_quarter", y="active_cases", color="circuit",
                markers=True,
                color_discrete_map=aq_color_map,
                labels={"year_quarter": "Quarter", "active_cases": "Active cases"},
            )
            fig_line = apply_common_layout(
                fig_line, height=400,
                title="Active caseload trajectories by circuit"
            )
            fig_line.update_xaxes(tickangle=-45, range=["2023-Q1", None])
            st.plotly_chart(fig_line, use_container_width=True)
        else:
            st.info("No active-case data matching selected filters.")
    else:
        st.info("Quarterly active caseload data not available.")

    st.subheader("Current total active cases by circuit")

    _snap = pd.DataFrame()
    if not circuit_snap.empty and any(c in circuit_snap.columns for c in ["active_cases", "active_cases_count"]):
        _snap = circuit_snap.copy()
        _snap["_active"] = _snap.get("active_cases", _snap.get("active_cases_count"))
    elif not backlog_cq.empty and "active_cases" in backlog_cq.columns:
        latest_q = backlog_cq["year_quarter"].max()
        _snap = backlog_cq[backlog_cq["year_quarter"] == latest_q][["circuit", "active_cases"]].copy()
        _snap["_active"] = _snap["active_cases"]

    if not _snap.empty:
        _snap = _fc(_snap)
        _snap = _snap.dropna(subset=["_active"]).sort_values("_active", ascending=False)

        col1, col2 = st.columns(2)

        with col1:
            snap_color_map = {str(c): CIRCUIT_COLORS.get(_norm_circuit(str(c)), "#aaaaaa") for c in _snap["circuit"].unique()}
            _snap["circuit_str"] = _snap["circuit"].astype(str)
            fig_bar = px.bar(
                _snap, x="circuit_str", y="_active",
                color="circuit_str",
                color_discrete_map=snap_color_map,
                labels={"circuit_str": "Circuit", "_active": "Active cases"},
            )
            fig_bar = apply_common_layout(
                fig_bar, height=360, title="Active cases by circuit (snapshot)"
            )
            fig_bar.update_layout(showlegend=False)
            st.plotly_chart(fig_bar, use_container_width=True)

        with col2:
            fig_map = static_choropleth_map(
                    df=_snap.rename(columns={"_active": "active_cases"}),
                    metric_col="active_cases",
                    title="Active cases — circuit map",
                )
            st.plotly_chart(fig_map, use_container_width=True)

        total_active = int(_snap["_active"].sum())
        st.metric("Total active cases (all circuits combined)", f"{total_active:,}")

        if not circuit_snap.empty and "avg_resolution_days" in circuit_snap.columns:
            st.subheader("Average resolution days by circuit")
            rs = _fc(circuit_snap).dropna(subset=["avg_resolution_days"]).sort_values(
                "avg_resolution_days", ascending=False
            )
            rs["circuit_str"] = rs["circuit"].astype(str)
            rs_color_map = {str(c): CIRCUIT_COLORS.get(_norm_circuit(str(c)), "#aaaaaa") for c in rs["circuit"].unique()}
            fig_res = px.bar(
                rs, x="circuit_str", y="avg_resolution_days",
                color="circuit_str",
                color_discrete_map=rs_color_map,
                labels={"circuit_str": "Circuit", "avg_resolution_days": "Avg. resolution (days)"},
            )
            fig_res = apply_common_layout(
                fig_res, height=340, title="Average resolution time by circuit"
            )
            fig_res.update_layout(showlegend=False)
            st.plotly_chart(fig_res, use_container_width=True)
    else:
        st.info("Snapshot active-case data not available.")

# =============================================================================
# PAGE: Jurisdiction Metrics
# =============================================================================

elif page == "Jurisdiction Metrics":

    JURISDICTION_LABELS = {
        "F":     "Federal Appellate",
        "FB":    "Federal Bankruptcy",
        "FBP":   "Federal Bankruptcy Panel",
        "FD":    "Federal District",
        "FS":    "Federal Special",
        "S":     "State",
        "other": "Other / Unknown",
    }

    section(
        "Jurisdiction metrics — snapshot & trends",
        "Backlog accumulation, inflow/outflow, active cases, and clearance analytics "
        "broken down by jurisdiction type across quarters.",
    )

    if jurisdiction_backlog.empty or "jurisdiction" not in jurisdiction_backlog.columns:
        st.info(
            "Jurisdiction data not available. Ensure jurisdiction_backlog_evolution.parquet "
            "contains a `jurisdiction` column."
        )
    else:
        jur_df = jurisdiction_backlog.copy()
        jur_df["jurisdiction_label"] = jur_df["jurisdiction"].map(JURISDICTION_LABELS).fillna(jur_df["jurisdiction"])

        jur_df_fq = _fq(jur_df, "year_quarter")

        all_jurisdictions = sorted(jur_df["jurisdiction_label"].dropna().unique())
        selected_jurisdictions = st.multiselect(
            "Filter jurisdictions", options=all_jurisdictions, default=all_jurisdictions,
        )

        jur_filtered = jur_df_fq[jur_df_fq["jurisdiction_label"].isin(selected_jurisdictions)].copy()

        if jur_filtered.empty:
            st.info("No data matching the selected filters.")
        else:
            jur_quarters = sorted(jur_filtered["year_quarter"].dropna().unique())
            snap_q = st.selectbox("Snapshot quarter", options=jur_quarters[::-1], index=0)
            snap = jur_filtered[jur_filtered["year_quarter"] == snap_q].copy()

            metric_candidates = [
                "total_backlog", "inflow_cases", "outflow_cases",
                "active_cases_count", "backlog_clearance_ratio", "clearance_efficiency",
            ]
            available_metrics = [c for c in metric_candidates if c in jur_filtered.columns]

            if not available_metrics:
                st.info("No numeric metrics found in the jurisdiction dataset.")
            else:
                snap_metric = st.selectbox(
                    "Select metric", options=available_metrics,
                    format_func=lambda c: c.replace("_", " ").title(),
                )

                # KPI strip
                st.subheader(f"Snapshot — {snap_q}")
                if not snap.empty and snap_metric in snap.columns:
                    kpi_cols = st.columns(len(snap))
                    for i, (_, row) in enumerate(snap.sort_values(snap_metric, ascending=False).iterrows()):
                        with kpi_cols[i]:
                            st.markdown("<div class='metric-card-container'>", unsafe_allow_html=True)
                            val = row[snap_metric]
                            fmt = f"{val:,.0f}" if abs(val) >= 1 else f"{val:.4f}"
                            st.metric(label=row["jurisdiction_label"], value=fmt)
                            st.markdown("</div>", unsafe_allow_html=True)

                # Bar chart
                if not snap.empty and snap_metric in snap.columns:
                    fig_bar = px.bar(
                        snap.dropna(subset=[snap_metric]).sort_values(snap_metric, ascending=False),
                        x="jurisdiction_label", y=snap_metric,
                        color="jurisdiction_label",
                        color_discrete_sequence=px.colors.qualitative.Set2,
                        labels={"jurisdiction_label": "Jurisdiction", snap_metric: snap_metric.replace("_", " ").title()},
                    )
                    fig_bar = apply_common_layout(
                        fig_bar, height=380,
                        title=f"{snap_metric.replace('_', ' ').title()} by jurisdiction — {snap_q}",
                    )
                    fig_bar.update_layout(showlegend=False)
                    st.plotly_chart(fig_bar, use_container_width=True)

                st.divider()
                st.subheader("Trends over time")

                agg = (
                    jur_filtered
                    .groupby(["year_quarter", "jurisdiction_label"])[snap_metric]
                    .sum().reset_index()
                )

                # Line chart
                fig_line = px.line(
                    agg, x="year_quarter", y=snap_metric, color="jurisdiction_label",
                    markers=True,
                    color_discrete_sequence=px.colors.qualitative.Set2,
                    labels={"year_quarter": "Quarter", snap_metric: snap_metric.replace("_", " ").title(), "jurisdiction_label": "Jurisdiction"},
                )
                if snap_metric == "backlog_clearance_ratio":
                    fig_line.add_hline(y=1.0, line_dash="dash", line_color="#666", annotation_text="equilibrium (1.0)")
                fig_line = apply_common_layout(fig_line, height=420, title=f"{snap_metric.replace('_', ' ').title()} by jurisdiction over time")
                fig_line.update_xaxes(tickangle=-45)
                st.plotly_chart(fig_line, use_container_width=True)

                # Stacked area (volume metrics only)
                if snap_metric in ("total_backlog", "inflow_cases", "outflow_cases", "active_cases_count"):
                    fig_area = px.area(
                        agg.sort_values("year_quarter"),
                        x="year_quarter", y=snap_metric, color="jurisdiction_label",
                        color_discrete_sequence=px.colors.qualitative.Set2,
                        labels={"year_quarter": "Quarter", snap_metric: snap_metric.replace("_", " ").title(), "jurisdiction_label": "Jurisdiction"},
                    )
                    fig_area = apply_common_layout(fig_area, height=380, title=f"{snap_metric.replace('_', ' ').title()} — stacked composition by jurisdiction")
                    fig_area.update_xaxes(tickangle=-45)
                    st.plotly_chart(fig_area, use_container_width=True)

                # Box plot (ratio metrics only)
                if snap_metric in ("backlog_clearance_ratio", "clearance_efficiency"):
                    fig_box = px.box(
                        jur_filtered.dropna(subset=[snap_metric]),
                        x="jurisdiction_label", y=snap_metric,
                        color="jurisdiction_label",
                        color_discrete_sequence=px.colors.qualitative.Set2,
                        labels={"jurisdiction_label": "Jurisdiction", snap_metric: snap_metric.replace("_", " ").title()},
                    )
                    if snap_metric == "backlog_clearance_ratio":
                        fig_box.add_hline(y=1.0, line_dash="dash", line_color="#666")
                    fig_box = apply_common_layout(fig_box, height=380, title=f"{snap_metric.replace('_', ' ').title()} — quarterly distribution by jurisdiction")
                    fig_box.update_layout(showlegend=False)
                    st.plotly_chart(fig_box, use_container_width=True)

                st.divider()

                # Raw table + download
                st.subheader("Quarter-by-quarter detail")
                display_cols = ["year_quarter", "jurisdiction_label"] + [c for c in metric_candidates if c in jur_filtered.columns]
                st.dataframe(jur_filtered[display_cols].sort_values(["jurisdiction_label", "year_quarter"]).reset_index(drop=True), use_container_width=True)
                st.download_button(
                    "Download jurisdiction data (CSV)",
                    data=jur_filtered[display_cols].to_csv(index=False),
                    file_name="jurisdiction_metrics.csv", mime="text/csv",
                )

# =============================================================================
# PAGE: Raw Tables
# =============================================================================

elif page == "Raw Tables":

    section("Raw analytical tables", "Direct access to circuit-quarterly Gold layer outputs.")

    table_map = {
        "circuit_backlog_quarterly":    backlog_cq,
        "clearance_circuit_quarterly":  clearance_cq,
        "active_circuit_quarterly":     active_cq,
        "circuit_snapshot":             circuit_snap,
        "court_backlog_evolution":      court_backlog,
        "jurisdiction_backlog_evolution": jurisdiction_backlog,
    }

    table_choice = st.selectbox("Choose data table", list(table_map.keys()))
    df_raw = table_map[table_choice].copy()

    if df_raw.empty:
        st.info("Selected table is empty or not available.")
    else:
        q_filter = st.text_input("Filter records (case-insensitive search across string columns)")
        if q_filter:
            mask = pd.Series(False, index=df_raw.index)
            for c in df_raw.select_dtypes(include=[object]).columns:
                mask = mask | df_raw[c].astype(str).str.contains(q_filter, case=False, na=False)
            df_raw = df_raw.loc[mask]

        st.write(f"Total rows: {len(df_raw):,}")
        csv = df_raw.to_csv(index=False)
        st.download_button(
            label="Download Table CSV", data=csv,
            file_name=f"{table_choice}.csv", mime="text/csv"
        )
        st.dataframe(df_raw, use_container_width=True)


# =============================================================================
# Footer Info
# =============================================================================

st.divider()

with st.expander("Methodology & data notes"):
    st.markdown(
        """
### Circuit Quarterly Dashboard — data sources

All analytics derive from Gold-level representations inside the Medallion pipeline architecture:

| Table | Source file | Key metrics |
|---|---|---|
| `CIRCUIT_BACKLOG_EVOLUTION` | `circuit_backlog_evolution.parquet` | backlog, net_change, clearance_efficiency, backlog_clearance_ratio |
| `CLEARANCE_RATE_CIRCUIT_BY_QUARTER` | `clearance_rate_circuit_by_quarter.parquet` | backlog_clearance_rate_pct |
| `ACTIVE_CASES_BY_CIRCUIT_QUARTER` | `active_cases_by_circuit_quarter.parquet` | active_cases_count |
| `METRICS_BY_CIRCUIT` | `circuit_performance_metrics.parquet` | active_cases, avg_resolution_days |
| `COURT_BACKLOG_EVOLUTION` | `court_backlog_evolution.parquet` | backlog, inflow, outflow |
| `JURISDICTION_BACKLOG_EVOLUTION` | `juris_backlog_evolution.parquet` | backlog, inflow, outflow |

### Key Definitions

- **Backlog** — Cumulative net unresolved cases (running sum of net_change since 2023, but counting active cases since 2020).
- **Backlog clearance ratio** — `outflow / inflow`. Ratios below 1 indicating system backlog growth.
- **Clearance efficiency** — `outflow / backlog`. Tracks the relative resolution of standing inventory per quarter.
- **Net change** — `inflow − outflow`. Positive values signal backlog addition.
"""
    )