"""
Circuit Quarterly Dashboard
============================
Focused on circuit × year-quarter analytics:
  - Animated maps: clearance_efficiency, backlog_clearance_ratio, total_backlog by circuit × quarter
  - Total active cases map and breakdown
  - Clearance efficiency heatmap across circuits and quarters
  - Backlog clearance ratio trends and distributions
  - Active caseload decomposition

Parquet sources (all under gold/metrics/):
  CIRCUIT_BACKLOG_EVOLUTION       → circuit_backlog_evolution.parquet
  CLEARANCE_RATE_CIRCUIT_QUARTER  → clearance_rate_circuit_by_quarter.parquet
  ACTIVE_CASES_BY_CIRCUIT_QUARTER → active_cases_by_circuit_quarter.parquet
  METRICS_BY_CIRCUIT              → circuit_performance_metrics.parquet
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
# Page config
# =============================================================================

st.set_page_config(
    page_title="Circuit Quarterly Dashboard",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# =============================================================================
# Paths
# =============================================================================

BASE_DIR = Path(__file__).resolve().parent
GOLD_DIR = BASE_DIR / "gold" / "metrics"


# =============================================================================
# Color semantics  (mirrored from original dashboard)
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

# US Federal Circuit centroids (same as original)
CIRCUIT_CENTROIDS = {
    "1":   {"lat": 42.36,  "lon": -71.06,  "label": "1st Circuit",  "states": "ME, MA, NH, RI, PR"},
    "2":   {"lat": 40.71,  "lon": -74.01,  "label": "2nd Circuit",  "states": "CT, NY, VT"},
    "3":   {"lat": 39.95,  "lon": -75.17,  "label": "3rd Circuit",  "states": "DE, NJ, PA, VI"},
    "4":   {"lat": 38.89,  "lon": -77.03,  "label": "4th Circuit",  "states": "MD, NC, SC, VA, WV"},
    "5":   {"lat": 29.76,  "lon": -95.37,  "label": "5th Circuit",  "states": "LA, MS, TX"},
    "6":   {"lat": 39.10,  "lon": -84.51,  "label": "6th Circuit",  "states": "KY, MI, OH, TN"},
    "7":   {"lat": 41.88,  "lon": -87.63,  "label": "7th Circuit",  "states": "IL, IN, WI"},
    "8":   {"lat": 44.98,  "lon": -93.27,  "label": "8th Circuit",  "states": "AR, IA, MN, MO, NE, ND, SD"},
    "9":   {"lat": 37.77,  "lon": -122.42, "label": "9th Circuit",  "states": "AK, AZ, CA, HI, ID, MT, NV, OR, WA"},
    "10":  {"lat": 39.74,  "lon": -104.98, "label": "10th Circuit", "states": "CO, KS, NM, OK, UT, WY"},
    "11":  {"lat": 33.75,  "lon": -84.39,  "label": "11th Circuit", "states": "AL, FL, GA"},
    "dc":  {"lat": 38.91,  "lon": -77.04,  "label": "DC Circuit",   "states": "DC"},
    "fc": {"lat": 38.89,  "lon": -77.05,  "label": "Fed. Circuit", "states": "National"},
}


# State abbreviation → circuit key  (US states + DC; territories omitted from map)
STATE_TO_CIRCUIT: dict[str, str] = {
    # 1st
    "ME": "1", "MA": "1", "NH": "1", "RI": "1",
    # 2nd
    "CT": "2", "NY": "2", "VT": "2",
    # 3rd
    "DE": "3", "NJ": "3", "PA": "3",
    # 4th
    "MD": "4", "NC": "4", "SC": "4", "VA": "4", "WV": "4",
    # 5th
    "LA": "5", "MS": "5", "TX": "5",
    # 6th
    "KY": "6", "MI": "6", "OH": "6", "TN": "6",
    # 7th
    "IL": "7", "IN": "7", "WI": "7",
    # 8th
    "AR": "8", "IA": "8", "MN": "8", "MO": "8", "NE": "8", "ND": "8", "SD": "8",
    # 9th
    "AK": "9", "AZ": "9", "CA": "9", "HI": "9", "ID": "9",
    "MT": "9", "NV": "9", "OR": "9", "WA": "9",
    # 10th
    "CO": "10", "KS": "10", "NM": "10", "OK": "10", "UT": "10", "WY": "10",
    # 11th
    "AL": "11", "FL": "11", "GA": "11",
    # DC Circuit
    "DC": "dc",
}

# One distinct colour per circuit (qualitative, colour-blind friendly)
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
    for key in CIRCUIT_CENTROIDS:
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


def section(title: str, intro: str | None = None):
    st.divider()
    st.header(title)
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


def _geo_layout(fig: go.Figure, title: str, height: int = 520) -> go.Figure:
    fig.update_geos(
        scope="usa",
        showland=True,
        landcolor="#f0f0f0",
        showcoastlines=True,
        coastlinecolor="#cccccc",
        showsubunits=True,
        subunitcolor="#e0e0e0",
        showlakes=False,
        projection_type="albers usa",
    )
    fig.update_layout(
        title=dict(text=title, x=0.01, font=dict(size=13)),
        height=height,
        margin=dict(l=0, r=0, t=50, b=0),
        template="plotly_white",
        font=dict(family="Arial", size=11),
    )
    return fig


def _build_state_choropleth_df(
    circuit_df: pd.DataFrame,
    metric_col: str,
) -> pd.DataFrame:
    """
    Expand a circuit-level dataframe into a state-level dataframe for choropleth.
    Each state gets:
      - circuit_key   : the normalised circuit key
      - circuit_label : human-readable label
      - circuit_color : distinct hex colour for that circuit
      - metric_value  : the circuit metric (same value for every state in the circuit)
      - metric_norm   : 0-1 normalised metric (used for opacity / annotation)
    Extra columns from circuit_df are forwarded as-is.
    """
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


def _choropleth_geo_layout(fig: go.Figure, title: str, height: int = 520) -> go.Figure:
    fig.update_geos(
        scope="usa",
        showland=True,
        landcolor="#f5f5f5",
        showcoastlines=True,
        coastlinecolor="#999999",
        showsubunits=True,
        subunitcolor="#cccccc",
        showlakes=False,
        projection_type="albers usa",
    )
    fig.update_layout(
        title=dict(text=title, x=0.01, font=dict(size=13)),
        height=height,
        margin=dict(l=0, r=0, t=50, b=0),
        template="plotly_white",
        font=dict(family="Arial", size=11),
    )
    return fig


def static_choropleth_map(
    df: pd.DataFrame,
    metric_col: str,
    title: str,
    height: int = 500,
) -> go.Figure:
    """
    Choropleth map where each circuit has a distinct colour.
    Metric is shown via marker opacity on centroid dots + hover tooltip.
    """
    state_df = _build_state_choropleth_df(df, metric_col)
    if state_df.empty:
        return go.Figure()

    # One trace per circuit so each gets its own discrete legend entry
    fig = go.Figure()

    circuits_present = state_df["circuit_key"].unique()
    for key in sorted(circuits_present, key=lambda x: (len(x), x)):
        sub = state_df[state_df["circuit_key"] == key]
        label = CIRCUIT_CENTROIDS.get(key, {}).get("label", key)
        color = CIRCUIT_COLORS.get(key, "#aaaaaa")
        metric_val = sub["metric_value"].iloc[0]

        # Filled state areas via Choropleth (one trace per circuit)
        fig.add_trace(go.Choropleth(
            locations=sub["state"],
            z=sub["metric_norm"],
            locationmode="USA-states",
            # CHANGE THIS LINE:
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
        dot_size = 8 + (v - v.min()) / (v_max - v.min() + 1e-9) * 20

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
            # Inside _make_circuit_traces, within the Scattergeo trace:
            # Inside static_choropleth_map, within the Scattergeo trace:
            textfont=dict(size=12, color="#333333"), # Increased size
            marker=dict(
                # Increased the base size (12) and the multiplier (30)
                size=12 + (v - v.min()) / (v_max - v.min() + 1e-9) * 30, 
                color=[CIRCUIT_COLORS.get(_norm_circuit(str(c)), "#888") for c in geo["circuit"]],
                line=dict(width=1.2, color="white"),
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
    # Convert base_color (e.g., '#4e79a7') to an RGB tuple (0-1 range)
    rgb = mcolors.to_rgb(base_color)
    
    # Create the rgba strings
    # 0.26 is approx 0x44 (68/255)
    # 0.93 is approx 0xee (238/255)
    c1 = f"rgba({rgb[0]*255:.0f}, {rgb[1]*255:.0f}, {rgb[2]*255:.0f}, 0.26)"
    c2 = f"rgba({rgb[0]*255:.0f}, {rgb[1]*255:.0f}, {rgb[2]*255:.0f}, 0.93)"
    
    return [[0, c1], [1, c2]]
def animated_choropleth_map(
    df: pd.DataFrame,
    metric_col: str,
    quarter_col: str,
    title: str,
    height: int = 540,
    hover_extras: list[str] | None = None,
) -> go.Figure:
    """
    Animated choropleth map driven by quarter_col.
    States are filled with distinct circuit colours; metric encoded via opacity + centroid dots.
    Uses px.choropleth for the animation frames, with a scatter_geo overlay for centroid labels.
    """
    if df.empty or metric_col not in df.columns:
        return go.Figure()

    quarters = sorted(df[quarter_col].dropna().unique())
    if not quarters:
        return go.Figure()

    # Build full state-expanded dataframe with all quarters
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

    # We use plotly graph_objects frames for full control
    fig = go.Figure()

    def _make_circuit_traces(q: str) -> list[go.Trace]:
        sub_all = all_states[all_states[quarter_col] == q]
        traces: list[go.BaseTraceType] = []

        for key in sorted(set(STATE_TO_CIRCUIT.values()), key=lambda x: (len(x), x)):
            sub = sub_all[sub_all["circuit_key"] == key]
            if sub.empty:
                continue
            label = CIRCUIT_CENTROIDS.get(key, {}).get("label", key)
            color = CIRCUIT_COLORS.get(key, "#aaaaaa")
            traces.append(go.Choropleth(
                locations=sub["state"],
                z=sub["metric_norm"],
                locationmode="USA-states",
                colorscale = get_formatted_colorscale(color),
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

        # Centroid dots for this quarter
        geo = _enrich_with_geo(df[df[quarter_col] == q])
        if not geo.empty and metric_col in geo.columns:
            v = geo[metric_col].fillna(0).clip(lower=0)
            v_global_max = df[metric_col].fillna(0).clip(lower=0).max()
            dot_size = 8 + v / (v_global_max + 1e-9) * 22
            extras = hover_extras or []
            extra_text = geo.apply(
                lambda r: "".join(
                    f"<br>{e}: {_fmt_metric(r[e])}" for e in extras if e in r.index
                ),
                axis=1,
            )
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
                # Inside _make_circuit_traces, within the Scattergeo trace:
                textfont=dict(size=12, color="#222222"), # Increased label size
                marker=dict(
                # Increased the base size (12) and the multiplier (35)
                    size=12 + v / (v_global_max + 1e-9) * 35, 
                    color=[CIRCUIT_COLORS.get(_norm_circuit(str(c)), "#888") for c in geo["circuit"]],
                    line=dict(width=1.2, color="white"),
                    opacity=0.92,
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

    # First frame (initial state)
    for t in _make_circuit_traces(quarters[0]):
        fig.add_trace(t)

    # Animation frames
    fig.frames = [
        go.Frame(
            data=_make_circuit_traces(q),
            name=str(q),
            layout=go.Layout(title_text=f"{title} — {q}"),
        )
        for q in quarters
    ]

    # Slider + play/pause
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
        margin=dict(l=0, r=0, t=60, b=80),
        legend=dict(
            title="Circuit",
            orientation="v",
            x=1.01, y=0.7,
            xanchor="left",
            font=dict(size=9),
            itemsizing="constant",
        ),
        showlegend=True,
    )
    return fig


def _fmt_metric(v) -> str:
    """Format a metric value compactly for map labels."""
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
    """CIRCUIT_BACKLOG_EVOLUTION — year_quarter, circuit, inflow, outflow,
       active_cases, net_change, backlog, clearance_efficiency, backlog_clearance_ratio"""
    candidates = [
        GOLD_DIR / "backlog_evolution_circuit_by_quarter.parquet",
        GOLD_DIR.parent / "circuit_backlog_evolution.parquet",
    ]
    for p in candidates:
        if p.exists():
            return pd.read_parquet(p)
    return pd.DataFrame()


@st.cache_data
def load_clearance_circuit_quarterly() -> pd.DataFrame:
    """clearance_rate_circuit_by_quarter — year_quarter, circuit,
       inflow, outflow, backlog_clearance_rate, backlog_clearance_rate_pct"""
    candidates = [
        GOLD_DIR / "backlog_evolution_circuit_by_quarter.parquet",
        GOLD_DIR / "clearance_rate_by_quarter.parquet",
    ]
    for p in candidates:
        if p.exists():
            df = pd.read_parquet(p)
            if "circuit" in df.columns:
                return df
    return pd.DataFrame()


@st.cache_data
def load_active_circuit_quarterly() -> pd.DataFrame:
    """ACTIVE_CASES_BY_CIRCUIT_QUARTER — circuit, active_quarter, active_cases_count"""
    p = GOLD_DIR / "active_cases_by_circuit_quarter.parquet"
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()


@st.cache_data
def load_active_circuit_static() -> pd.DataFrame:
    """ACTIVE_CASES_BY_COURT (circuit-level if available) or METRICS_BY_CIRCUIT"""
    candidates = [
        GOLD_DIR / "circuit_performance_metrics.parquet",
        GOLD_DIR / "metrics_by_circuit.parquet",
    ]
    for p in candidates:
        if p.exists():
            return pd.read_parquet(p)
    return pd.DataFrame()


# =============================================================================
# Load data
# =============================================================================

backlog_cq   = load_circuit_backlog_quarterly()
clearance_cq = load_clearance_circuit_quarterly()
active_cq    = load_active_circuit_quarterly()
circuit_snap = load_active_circuit_static()


# =============================================================================
# Sidebar
# =============================================================================

st.sidebar.title("⚖️ Circuit Quarterly")

page = st.sidebar.radio(
    "View",
    [
        "Maps — Animated",
        "Maps — Snapshot",
        "Backlog & Clearance Trends",
        "Active Cases",
        "Heatmaps",
        "Raw Tables",
    ],
)

# Collect all circuits across loaded frames
_all_circuits: list[str] = []
for _df in [backlog_cq, clearance_cq, active_cq, circuit_snap]:
    if not _df.empty and "circuit" in _df.columns:
        _all_circuits += [str(c) for c in _df["circuit"].dropna().unique()]
all_circuits = sorted(set(_all_circuits))

selected_circuits = st.sidebar.multiselect(
    "Circuits", options=all_circuits, default=all_circuits
)

# Quarter range filter — derive from backlog_cq primarily
_qcol_main = "year_quarter"
_quarters: list[str] = []
for _df, _col in [
    (backlog_cq,   "year_quarter"),
    (clearance_cq, next((c for c in clearance_cq.columns if "quarter" in c.lower()), "")),
    (active_cq,    next((c for c in active_cq.columns    if "quarter" in c.lower()), "")),
]:
    if not _df.empty and _col and _col in _df.columns:
        _quarters += [str(q) for q in _df[_col].dropna().unique()]
all_quarters = sorted(set(_quarters))

if len(all_quarters) >= 2:
    q_range = st.sidebar.select_slider(
        "Quarter range", options=all_quarters, value=(all_quarters[0], all_quarters[-1])
    )
else:
    q_range = (all_quarters[0], all_quarters[-1]) if len(all_quarters) == 2 else (None, None)


def _fq(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Filter dataframe to selected quarter range."""
    if q_range[0] is None or col not in df.columns:
        return df
    return df[df[col].between(q_range[0], q_range[1])].copy()


def _fc(df: pd.DataFrame) -> pd.DataFrame:
    """Filter dataframe to selected circuits."""
    if "circuit" in df.columns and selected_circuits:
        return df[df["circuit"].astype(str).isin(selected_circuits)].copy()
    return df


# =============================================================================
# Main title
# =============================================================================

st.title("Circuit Quarterly Dashboard")
st.caption(
    "Circuit-level judicial analytics — backlog accumulation, clearance efficiency, "
    "and active caseload across US federal circuits by quarter."
)


# =============================================================================
# PAGE: Maps — Animated
# =============================================================================

if page == "Maps — Animated":

    section(
        "Animated circuit maps by quarter",
        "Each frame represents one year-quarter. Use the play button or scrub the slider "
        "to watch metrics evolve across the 13 US federal circuits.",
    )

    # --- pick which metric to animate ---
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
            "or active_cases_by_circuit_quarter.parquet is present in the gold/metrics/ directory."
        )
    else:
        metric_name = st.selectbox("Metric to animate", list(anim_options.keys()))
        cfg = anim_options[metric_name]

        df_anim = _fq(_fc(cfg["df"]), cfg["qcol"])
        # clip negative sizes
        if cfg["size"] in df_anim.columns:
            df_anim[cfg["size"]] = df_anim[cfg["size"]].clip(lower=0)

        if df_anim.empty:
            st.info("No data for selected circuits / quarters.")
        else:
            fig_anim = animated_choropleth_map(
                df=df_anim,
                metric_col=cfg["color"],
                quarter_col=cfg["qcol"],
                title=f"{metric_name} across US federal circuits — quarter by quarter",
                hover_extras=[c for c in cfg["extras"] if c in df_anim.columns],
            )
            st.plotly_chart(fig_anim, use_container_width=True)
            st.caption(
                "States are filled with each circuit's distinct colour. "
                "Centroid dot size and label encode the selected metric value per quarter. "
                "Use the play button or scrub the slider to animate over quarters."
            )

        # -- supplementary table for the latest quarter shown --
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
        "Single-quarter bubble map. Choose a quarter to display a static snapshot "
        "of any circuit-level metric.",
    )

    if backlog_cq.empty and circuit_snap.empty:
        st.info("No circuit-level data available for snapshot map.")
    else:
        # pick quarter
        snap_quarters = all_quarters or []
        if snap_quarters:
            snap_q = st.selectbox("Quarter", options=snap_quarters[::-1], index=0)
        else:
            snap_q = None

        # pick metric
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
            st.info("No suitable numeric metric found for snapshot map.")
        else:
            snap_metric = st.selectbox("Metric", options=snap_metric_options)

            color_scales_snap = {
                "backlog":                 "Oranges",
                "clearance_efficiency":    "RdYlGn",
                "backlog_clearance_ratio": "RdBu",
                "inflow":                  "Blues",
                "outflow":                 "Greens",
                "active_cases":            "Blues",
                "active_cases_count":      "Blues",
                "avg_resolution_days":     "Purples",
                "net_change":              "RdYlGn_r",
            }

            if "year_quarter" in _snap_df.columns and snap_q:
                snap_data = _snap_df[_snap_df["year_quarter"] == snap_q].copy()
            else:
                snap_data = _snap_df.copy()

            snap_data = _fc(snap_data)

            if snap_data.empty or snap_metric not in snap_data.columns:
                st.info("No data for the selected quarter / metric combination.")
            else:
                snap_data[snap_metric] = snap_data[snap_metric].clip(lower=0)
                fig_snap = static_choropleth_map(
                    df=snap_data,
                    metric_col=snap_metric,
                    title=f"{snap_metric.replace('_', ' ').title()} by circuit"
                          + (f" — {snap_q}" if snap_q else ""),
                )
                st.plotly_chart(fig_snap, use_container_width=True)

                # bar chart companion
                bar_df = snap_data.dropna(subset=[snap_metric]).sort_values(snap_metric, ascending=False)
                fig_bar = px.bar(
                    bar_df,
                    x="circuit",
                    y=snap_metric,
                    color=snap_metric,
                    color_continuous_scale=color_scales_snap.get(snap_metric, "Blues"),
                    labels={"circuit": "Circuit", snap_metric: snap_metric.replace("_", " ").title()},
                )
                fig_bar = apply_common_layout(
                    fig_bar, height=360,
                    title=f"{snap_metric.replace('_', ' ').title()} — circuit ranking"
                )
                fig_bar.update_coloraxes(showscale=False)
                st.plotly_chart(fig_bar, use_container_width=True)
                st.caption(
                    "Each circuit is shown in a distinct colour across its member states. "
                    "Centroid dot size encodes the metric value — larger dots indicate higher values. "
                    "The bar chart below ranks circuits from highest to lowest."
                )


# =============================================================================
# PAGE: Backlog & Clearance Trends
# =============================================================================

elif page == "Backlog & Clearance Trends":

    section(
        "Backlog and clearance analytics — circuit × quarter",
        "Quarterly time-series of backlog accumulation, clearance ratio, and clearance efficiency "
        "broken down by circuit.",
    )

    # ---- 1. Backlog evolution ----
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
            st.caption(
                "Each line represents a federal circuit. Upward trends indicate persistent "
                "imbalance between incoming and resolved cases."
            )

            # Stacked area
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
            st.caption("Stacked view shows each circuit's contribution to total system backlog over time.")
        else:
            st.info("No backlog data for the selected circuits / quarters.")
    else:
        st.info("Circuit backlog evolution data not available (circuit_backlog_evolution.parquet).")

    # ---- 2. Backlog clearance ratio ----
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
                st.caption(
                    "Circuits persistently below the dashed equilibrium line are accumulating backlog. "
                    "Ratio > 1 indicates the circuit resolved more cases than it received that quarter."
                )

                # Box distribution
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
                st.caption("Wide boxes indicate volatile quarterly clearance performance within that circuit.")
            else:
                st.info("No clearance ratio data for the selected filters.")
    else:
        st.info("Backlog clearance ratio data not available.")

    # ---- 3. Clearance efficiency ----
    st.subheader("Clearance efficiency by circuit")
    st.markdown(
        "_Clearance efficiency = outflow / backlog. Measures how much of the existing "
        "cumulative backlog is resolved in a given quarter._"
    )

    _eff_df = pd.DataFrame()
    if not backlog_cq.empty and "clearance_efficiency" in backlog_cq.columns:
        _eff_df = backlog_cq
    elif not clearance_cq.empty and "clearance_efficiency" in clearance_cq.columns:
        _eff_df = clearance_cq

    if not _eff_df.empty:
        qcol_eff = "year_quarter" if "year_quarter" in _eff_df.columns else next(
            (c for c in _eff_df.columns if "quarter" in c.lower()), None
        )
        if qcol_eff:
            eff = _fq(_fc(_eff_df), qcol_eff)
            if not eff.empty and "clearance_efficiency" in eff.columns:
                fig = px.line(
                    eff, x=qcol_eff, y="clearance_efficiency", color="circuit",
                    markers=True,
                    color_discrete_sequence=px.colors.qualitative.Set2,
                    labels={qcol_eff: "Quarter", "clearance_efficiency": "Clearance efficiency (outflow / backlog)"},
                )
                fig = apply_common_layout(
                    fig, height=420,
                    title="Quarterly clearance efficiency by circuit"
                )
                fig.update_xaxes(tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)
                st.caption(
                    "Higher efficiency means a larger share of the standing backlog was resolved that quarter. "
                    "Declining efficiency signals growing congestion relative to resolution capacity."
                )
            else:
                st.info("Clearance efficiency column not found in the data.")
    else:
        st.info("Clearance efficiency data not available (column 'clearance_efficiency' missing).")

    # ---- 4. Net change (inflow − outflow) ----
    if not backlog_cq.empty and "net_change" in backlog_cq.columns:
        st.subheader("Quarterly net change by circuit (inflow − outflow)")
        nc = _fq(_fc(backlog_cq), "year_quarter")
        if not nc.empty:
            fig_nc = px.line(
                nc, x="year_quarter", y="net_change", color="circuit",
                markers=True,
                color_discrete_sequence=px.colors.qualitative.Set2,
                labels={"year_quarter": "Quarter", "net_change": "Net change (cases)"},
            )
            fig_nc.add_hline(y=0, line_dash="dash", line_color="#666")
            fig_nc = apply_common_layout(
                fig_nc, height=380,
                title="Net case flow (inflow − outflow) by circuit"
            )
            fig_nc.update_xaxes(tickangle=-45)
            st.plotly_chart(fig_nc, use_container_width=True)
            st.caption(
                "Positive net change means more cases filed than resolved, "
                "contributing to backlog accumulation."
            )


# =============================================================================
# PAGE: Active Cases
# =============================================================================

elif page == "Active Cases":

    section(
        "Active caseload — circuits and quarters",
        "Cases that remain open (filed after 2020 and not yet terminated), "
        "tracked by circuit across quarters.",
    )

    # ---- 1. Animated / time-series of active cases ----
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

        if not aq.empty:
            # Stacked area
            fig_area = px.area(
                aq.sort_values("year_quarter"),
                x="year_quarter", y="active_cases", color="circuit",
                color_discrete_sequence=px.colors.qualitative.Set2,
                labels={"year_quarter": "Quarter", "active_cases": "Active cases"},
            )
            fig_area = apply_common_layout(
                fig_area, height=400,
                title="Active caseload by circuit (stacked area)"
            )
            fig_area.update_xaxes(tickangle=-45)
            st.plotly_chart(fig_area, use_container_width=True)
            st.caption(
                "Active caseload includes cases that were open at any point during the quarter. "
                "Sustained growth signals system-wide congestion."
            )

            # Line chart
            fig_line = px.line(
                aq, x="year_quarter", y="active_cases", color="circuit",
                markers=True,
                color_discrete_sequence=px.colors.qualitative.Set2,
                labels={"year_quarter": "Quarter", "active_cases": "Active cases"},
            )
            fig_line = apply_common_layout(
                fig_line, height=400,
                title="Active caseload trajectories by circuit"
            )
            fig_line.update_xaxes(tickangle=-45)
            st.plotly_chart(fig_line, use_container_width=True)
        else:
            st.info("No active-case data for the selected circuits / quarters.")
    else:
        st.info(
            "Quarterly active caseload data not available "
            "(active_cases_by_circuit_quarter.parquet or circuit_backlog_evolution.parquet)."
        )

    # ---- 2. Static snapshot: total active cases by circuit ----
    st.subheader("Current total active cases by circuit")

    _snap = pd.DataFrame()
    if not circuit_snap.empty and any(c in circuit_snap.columns for c in ["active_cases", "active_cases_count"]):
        _snap = circuit_snap.copy()
        _snap["_active"] = _snap.get("active_cases", _snap.get("active_cases_count"))
    elif not backlog_cq.empty and "active_cases" in backlog_cq.columns:
        # use most recent quarter
        latest_q = backlog_cq["year_quarter"].max()
        _snap = backlog_cq[backlog_cq["year_quarter"] == latest_q][["circuit", "active_cases"]].copy()
        _snap["_active"] = _snap["active_cases"]

    if not _snap.empty:
        _snap = _fc(_snap)
        _snap = _snap.dropna(subset=["_active"]).sort_values("_active", ascending=False)

        col1, col2 = st.columns(2)

        with col1:
            fig_bar = px.bar(
                _snap, x="circuit", y="_active",
                color="_active",
                color_continuous_scale="Blues",
                labels={"circuit": "Circuit", "_active": "Active cases"},
            )
            fig_bar = apply_common_layout(
                fig_bar, height=360, title="Active cases by circuit (snapshot)"
            )
            fig_bar.update_coloraxes(showscale=False)
            st.plotly_chart(fig_bar, use_container_width=True)

        with col2:
            fig_map = static_choropleth_map(
                    df=_snap.rename(columns={"_active": "active_cases"}),
                    metric_col="active_cases",
                    title="Active cases — circuit map",
                )
            st.plotly_chart(fig_map, use_container_width=True)

        total_active = int(_snap["_active"].sum())
        st.metric("Total active cases (all circuits)", f"{total_active:,}")

        if not circuit_snap.empty and "avg_resolution_days" in circuit_snap.columns:
            st.subheader("Average resolution days by circuit")
            rs = _fc(circuit_snap).dropna(subset=["avg_resolution_days"]).sort_values(
                "avg_resolution_days", ascending=False
            )
            fig_res = px.bar(
                rs, x="circuit", y="avg_resolution_days",
                color="avg_resolution_days",
                color_continuous_scale="Purples",
                labels={"circuit": "Circuit", "avg_resolution_days": "Avg. resolution (days)"},
            )
            fig_res = apply_common_layout(
                fig_res, height=340, title="Average resolution time by circuit"
            )
            fig_res.update_coloraxes(showscale=False)
            st.plotly_chart(fig_res, use_container_width=True)
            st.caption(
                "Average resolution days computed on terminated cases only. "
                "Right-censoring may understate this figure for recently active circuits."
            )
    else:
        st.info("Snapshot active-case data not available.")


# =============================================================================
# PAGE: Heatmaps
# =============================================================================

elif page == "Heatmaps":

    section(
        "Circuit × quarter heatmaps",
        "Colour-encoded grid showing metric intensity for every circuit × quarter cell.",
    )

    def _make_heatmap(df: pd.DataFrame, qcol: str, val_col: str, title: str,
                      color_scale: str = "Oranges") -> go.Figure | None:
        pivot = df.pivot_table(index="circuit", columns=qcol, values=val_col, aggfunc="mean")
        if pivot.empty:
            return None
        fig = px.imshow(
            pivot,
            color_continuous_scale=color_scale,
            aspect="auto",
            labels=dict(x="Quarter", y="Circuit", color=val_col.replace("_", " ").title()),
            title=title,
        )
        fig.update_layout(
            height=420,
            template="plotly_white",
            margin=dict(l=30, r=16, t=40, b=30),
            font=dict(family="Arial", size=11),
        )
        fig.update_xaxes(tickangle=-45)
        return fig

    heatmap_targets = []

    if not backlog_cq.empty:
        bq_h = _fq(_fc(backlog_cq), "year_quarter")
        qcol_h = "year_quarter"
        for col, scale, caption in [
            ("backlog",                "Oranges",   "Darker cells indicate higher accumulated backlog in that circuit × quarter."),
            ("clearance_efficiency",   "RdYlGn",    "Green = higher efficiency (more backlog resolved). Red = low efficiency."),
            ("backlog_clearance_ratio","RdBu",       "Blue > 1 (resolving faster than filing). Red < 1 (accumulating backlog)."),
            ("net_change",             "RdYlGn_r",  "Red = net accumulation (inflow > outflow). Green = net resolution."),
        ]:
            if col in bq_h.columns:
                heatmap_targets.append((bq_h, qcol_h, col, scale, caption))

    if not clearance_cq.empty:
        cq_h = _fq(_fc(clearance_cq), next((c for c in clearance_cq.columns if "quarter" in c.lower()), ""))
        if "backlog_clearance_rate_pct" in cq_h.columns:
            heatmap_targets.append((
                cq_h,
                next(c for c in cq_h.columns if "quarter" in c.lower()),
                "backlog_clearance_rate_pct",
                "RdYlGn",
                "Clearance rate % heatmap — green = >100% (reducing backlog), red = <100%.",
            ))

    if not heatmap_targets:
        st.info(
            "No suitable data for heatmaps. "
            "Ensure circuit_backlog_evolution.parquet is available."
        )
    else:
        for df_h, qcol_h, val_col_h, scale_h, cap_h in heatmap_targets:
            fig_h = _make_heatmap(
                df_h, qcol_h, val_col_h,
                f"{val_col_h.replace('_', ' ').title()} — circuit × quarter",
                scale_h,
            )
            if fig_h:
                st.plotly_chart(fig_h, use_container_width=True)
                st.caption(cap_h)
            else:
                st.info(f"No data to display heatmap for {val_col_h}.")


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
    }

    table_choice = st.selectbox("Choose table", list(table_map.keys()))
    df_raw = table_map[table_choice].copy()

    if df_raw.empty:
        st.info("Selected table is empty or not available.")
    else:
        q_filter = st.text_input("Filter (text search across string columns)")
        if q_filter:
            mask = pd.Series(False, index=df_raw.index)
            for c in df_raw.select_dtypes(include=[object]).columns:
                mask = mask | df_raw[c].astype(str).str.contains(q_filter, case=False, na=False)
            df_raw = df_raw.loc[mask]

        st.write(f"Rows: {len(df_raw):,}")
        csv = df_raw.to_csv(index=False)
        st.download_button(
            label="Download CSV", data=csv,
            file_name=f"{table_choice}.csv", mime="text/csv"
        )
        st.dataframe(df_raw, use_container_width=True)


# =============================================================================
# Footer
# =============================================================================

st.divider()

with st.expander("Methodology & data notes"):
    st.markdown(
        """
### Circuit Quarterly Dashboard — data sources

All data originates from the Gold layer of a Medallion analytical pipeline:

| Table | Source file | Key metrics |
|---|---|---|
| `CIRCUIT_BACKLOG_EVOLUTION` | `circuit_backlog_evolution.parquet` | backlog, net_change, clearance_efficiency, backlog_clearance_ratio |
| `CLEARANCE_RATE_CIRCUIT_BY_QUARTER` | `clearance_rate_circuit_by_quarter.parquet` | backlog_clearance_rate_pct |
| `ACTIVE_CASES_BY_CIRCUIT_QUARTER` | `active_cases_by_circuit_quarter.parquet` | active_cases_count |
| `METRICS_BY_CIRCUIT` | `circuit_performance_metrics.parquet` | active_cases, avg_resolution_days |

### Metric definitions

- **Backlog** — cumulative net unresolved cases (running sum of net_change since 2020).
- **Backlog clearance ratio** — `outflow / inflow`; < 1 means the circuit accumulated backlog that quarter.
- **Clearance efficiency** — `outflow / backlog`; measures how quickly the standing backlog is being eaten away.
- **Net change** — `inflow − outflow`; positive values add to backlog.

### Methodological caveats

- Only cases filed after 2020 are included.
- Right-censoring: recent active cases have not yet terminated, so duration estimates are biased downward.
- Circuit centroids are representative geographic coordinates, not exact court locations.
"""
    )