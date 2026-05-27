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
    "backlog": "#ff7f0e",  # orange (congestion)
    "active": "#1f77b4",   # blue (active)
    "resolved": "#2ca02c", # green (resolved)
    "duration": "#9467bd", # purple (duration)
    "warning": "#ffbf00"   # amber (warnings)
}


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
            font=dict(size=10)
        )
    )

    if title:
        layout_args["title"] = dict(
            text=title,
            x=0.01,
            xanchor="left",
            font=dict(size=13)
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
    return safe_read_parquet(GOLD_DIR / "backlog_by_year.parquet")


@st.cache_data
def load_clearance():
    return safe_read_parquet(GOLD_DIR / "clearance_rate_by_year.parquet")


@st.cache_data
def load_court_performance():
    return safe_read_parquet(GOLD_DIR / "court_performance_metrics.parquet")


@st.cache_data
def load_case_metrics():
    return safe_read_parquet(GOLD_DIR / "case_metrics.parquet")


@st.cache_data
def load_backlog_enhanced():
    path = GOLD_DIR / "backlog_enhanced.parquet"
    if path.exists():
        return pd.read_parquet(path)
    return load_backlog()


@st.cache_data
def load_duration_quantiles():
    path = GOLD_DIR / "duration_quantiles_by_year.parquet"
    if path.exists():
        return pd.read_parquet(path)
    return pd.DataFrame()


@st.cache_data
def load_court_year_trends():
    path = GOLD_DIR / "court_year_trends.parquet"
    if path.exists():
        return pd.read_parquet(path)
    return pd.DataFrame()


@st.cache_data
def load_active_resolved():
    path = GOLD_DIR / "active_resolved_evolution.parquet"
    if path.exists():
        return pd.read_parquet(path)
    return pd.DataFrame()


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
# Load data
# =============================================================================

backlog = load_backlog()
backlog_enh = load_backlog_enhanced()
clearance = load_clearance()
performance = load_court_performance()
case_metrics = load_case_metrics()
duration_quantiles = load_duration_quantiles()
court_year_trends = load_court_year_trends()
active_resolved = load_active_resolved()


# =============================================================================
# Sidebar
# =============================================================================

st.sidebar.title("⚖️ Judicial Analytics")

page = st.sidebar.radio(
    "Navigation",
    [
        "Overview",
        "Backlog Analytics",
        "Court Performance",
        "Duration Analysis",
        "Raw Tables",
    ],
)

top_n = st.sidebar.slider("Top courts", min_value=5, max_value=50, value=20)

# temporal filters
years = sorted(backlog["year"].unique()) if not backlog.empty else [2020, 2026]
min_year, max_year = int(years[0]), int(years[-1])
year_range = st.sidebar.slider("Year range", min_value=min_year, max_value=max_year, value=(min_year, max_year))

# court type filter (if available)
court_types = []
if not case_metrics.empty and "jurisdiction_type" in case_metrics.columns:
    court_types = sorted(case_metrics["jurisdiction_type"].dropna().unique())
selected_court_types = st.sidebar.multiselect("Court types", options=court_types, default=court_types)

# active/resolved filter
show_active = st.sidebar.checkbox("Show active cases", value=True)
show_resolved = st.sidebar.checkbox("Show resolved cases", value=True)


# =============================================================================
# Main title
# =============================================================================

st.title("Judicial Analytics Dashboard")
st.caption("Analytical observatory of judicial congestion, court workload, backlog accumulation, and case resolution dynamics.")


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
    """
    )

    total_cases = len(case_metrics) if not case_metrics.empty else 0
    active_cases = int(performance["active_cases"].sum()) if not performance.empty else 0
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

    # -------------------------------------------------------------------------
    # KPI cards (compact)
    # -------------------------------------------------------------------------

    c1, c2, c3, c4, c5, c6 = st.columns([1, 1, 1, 1, 1, 1])
    c1.metric("Total cases", f"{total_cases:,}")
    c2.metric("Active cases", f"{active_cases:,}")
    c3.metric("Resolved cases", f"{resolved_cases:,}")
    c4.metric("Avg duration (days)", avg_duration)
    c5.metric("Current backlog", f"{latest_backlog:,}")
    c6.metric("Clearance % (latest)", latest_clearance)


    # -------------------------------------------------------------------------
    # Charts — denser two-up layout
    # -------------------------------------------------------------------------

    col1, col2 = st.columns([1, 1])

    # Backlog evolution (left)
    with col1:
        st.subheader("Backlog evolution")
        df_plot = (
            backlog_enh[backlog_enh["year"].between(year_range[0], year_range[1])]
            if not backlog_enh.empty
            else pd.DataFrame()
        )
        if not df_plot.empty:
            fig = px.bar(df_plot, x="year", y="backlog", color_discrete_sequence=[COLORS["backlog"]])
            fig = apply_common_layout(fig, height=340, title="Judicial backlog over time")
            fig.update_traces(marker_line_width=0)
            st.plotly_chart(fig, use_container_width=True)
            st.caption(
                """
            Backlog measures the accumulation of unresolved cases over time. 
            Sustained backlog growth suggests that new filings systematically exceed judicial resolution capacity.
            """
            )
        else:
            st.info("Backlog data not available.")

    # Inflow vs Outflow (right)
    with col2:
        st.subheader("Inflow vs Outflow")
        flow_df = (
            backlog_enh.loc[backlog_enh["year"].between(year_range[0], year_range[1]), ["year", "inflow", "outflow"]]
            if not backlog_enh.empty
            else pd.DataFrame()
        )
        if not flow_df.empty:
            flow_m = flow_df.melt(id_vars="year", var_name="flow_type", value_name="cases")
            color_map = {"inflow": COLORS["active"], "outflow": COLORS["resolved"]}
            fig = px.bar(
                flow_m, x="year", y="cases", color="flow_type", barmode="group", color_discrete_map=color_map
            )
            fig = apply_common_layout(fig, height=340, title="Case inflow and outflow")
            st.plotly_chart(fig, use_container_width=True)
            st.caption(
                """
            Comparing inflow and outflow highlights whether courts resolve cases fast enough to absorb new filings. 
            Persistent inflow > outflow contributes directly to backlog expansion.
            """
            )
        else:
            st.info("Inflow/outflow data not available.")

# -------------------------------------------------------------------------
# Judicial congestion dynamics
# -------------------------------------------------------------------------

    st.subheader("Judicial congestion dynamics")

    if not backlog_enh.empty:

        df_dyn = (
            backlog_enh
            .sort_values("year")
            .loc[
                backlog_enh["year"].between(year_range[0], year_range[1])
            ]
            .copy()
        )

        # congestion pressure ratio
        df_dyn["pressure_ratio"] = (
            df_dyn["inflow"] /
            df_dyn["outflow"].replace(0, np.nan)
        )

        fig = go.Figure()

        # pressure ratio
        fig_ratio = px.line(
            df_dyn,
            x="year",
            y="pressure_ratio",
            markers=True,
            color_discrete_sequence=[COLORS["backlog"]]
        )

        fig_ratio.add_hline(
            y=1,
            line_dash="dash",
            line_color="#666666"
        )

        fig_ratio = apply_common_layout(
            fig_ratio,
            height=300,
            title="Judicial pressure ratio (inflow / outflow)"
        )

        fig_ratio.update_yaxes(
            title_text="Pressure ratio",
            range=[0, 10]

        )

        st.plotly_chart(
            fig_ratio,
            use_container_width=True
        )

        st.caption(
            """
    A pressure ratio above 1 indicates that incoming cases exceed judicial
    resolution capacity, contributing to congestion growth.
    """
        )

    else:

        st.info(
            "Judicial congestion indicators are not available for the selected range."
        )


# =============================================================================
# Backlog analytics
# =============================================================================


elif page == "Backlog Analytics":

    section(
        "Judicial congestion indicators",
        "Temporal indicators describing judicial congestion, backlog accumulation, and court resolution capacity."
    )

    # Backlog
    df_backlog = backlog.copy() if not backlog.empty else pd.DataFrame()
    if not df_backlog.empty:
        fig = px.bar(df_backlog.loc[df_backlog["year"].between(year_range[0], year_range[1])], x="year", y="backlog", color_discrete_sequence=[COLORS["backlog"]])
        fig = apply_common_layout(fig, height=360, title="Backlog by year")
        fig.update_xaxes(range=[2019, 2026])
        st.plotly_chart(fig, use_container_width=True)

        st.caption(
            "The sharp increase in backlog after 2020 suggests persistent imbalance between incoming and resolved cases."
        )
    else:
        st.info("Backlog data not available.")

    # Clearance: raw + 3-year rolling mean
    if not clearance.empty:
        clr = clearance.dropna(subset=["clearance_rate_pct"]).sort_values("year").copy()
        clr = clr.loc[clr["year"].between(year_range[0], year_range[1])]
        if not clr.empty:
            clr["smoothed"] = clr["clearance_rate_pct"].rolling(window=3, center=True, min_periods=1).mean()
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=clr["year"], y=clr["clearance_rate_pct"], mode="lines+markers", name="Raw clearance", line=dict(color="#888888", width=1), marker=dict(size=6, opacity=0.7)))
            fig.add_trace(go.Scatter(x=clr["year"], y=clr["smoothed"], mode="lines", name="3-year smooth", line=dict(color=COLORS["backlog"], width=3)))
            fig = apply_common_layout(fig, height=380, title="Clearance rate (raw vs 3-year smoothed)")
            fig.update_yaxes(title_text="Clearance (%)")
            fig.update_yaxes(range=[0, 200])
            st.plotly_chart(fig, use_container_width=True)
            st.caption(
                "Clearance rates above 100% indicate periods where courts resolved more cases than they received."
            )

            # sparse-year warnings from duration_quantiles if present
            if not duration_quantiles.empty and "sparse_year_warning" in duration_quantiles.columns:
                dq_sel = duration_quantiles.loc[duration_quantiles["year"].between(year_range[0], year_range[1])]
                if dq_sel["sparse_year_warning"].any():
                    st.caption(
                        "Sparse historical resolutions may destabilize clearance estimates."
                    )
            else:
                st.info("Clearance rate shown with 3-year smoothing to reduce noise. Recent-year estimates are right-censored and may undercount terminations.")
        else:
            st.info("Clearance data not available for selected years.")
    else:
        st.info("Clearance data not available.")


# =============================================================================
# Court performance
# =============================================================================


elif page == "Court Performance":

    section("Court workload and efficiency", "Court-level performance indicators.")

    if performance.empty:
        st.info("Court performance metrics not available.")
    else:
        # filter by court_type if available
        perf = performance.copy()

        if "jurisdiction_type" in perf.columns and selected_court_types:
            perf = perf[
                perf["jurisdiction_type"].isin(selected_court_types)
            ]

        # remove courts without resolved cases
        # to avoid artificial duration statistics
        perf = perf.loc[
            perf["resolved_cases"] > 0
        ].copy()

        # remove extreme outliers for visualization readability
        perf = perf.loc[
            perf["active_cases"] <= perf["active_cases"].quantile(0.99)
        ]

        perf = perf.loc[
            perf["mean_duration"] <= perf["mean_duration"].quantile(0.99)
        ]

        # Horizontal bar: top active courts
        top_active = perf.sort_values(by="active_cases", ascending=False).head(top_n)
        if not top_active.empty:
            # clip x-axis to 95th percentile to avoid collapse by extreme outliers
            x95 = top_active["active_cases"].quantile(0.95)
            fig = px.bar(top_active.sort_values("active_cases"), x="active_cases", y="court_id", orientation="h", color_discrete_sequence=[COLORS["active"]])
            fig = apply_common_layout(fig, height=360, title="Top active courts (by active cases)")
            fig.update_xaxes(title_text="Active cases", range=[0, max(x95 * 1.2, top_active["active_cases"].max())])
            fig.update_yaxes(title_text="Court")
            st.plotly_chart(fig, use_container_width=True)
            st.caption(
                "A small subset of courts concentrates a disproportionately large share of active judicial workload."
            )

        # Horizontal bar: mean duration
        dur_clean = perf[perf["mean_duration"] > 0]
        if not dur_clean.empty:
            dtop = dur_clean.sort_values("mean_duration", ascending=True).head(top_n)
            y95 = dtop["mean_duration"].quantile(0.95)
            fig = px.bar(dtop, x="mean_duration", y="court_id", orientation="h", color_discrete_sequence=[COLORS["duration"]])
            fig = apply_common_layout(fig, height=360, title="Average case duration by court")
            fig.update_xaxes(title_text="Mean duration (days)", range=[0, max(y95 * 1.2, dtop["mean_duration"].max())])
            st.plotly_chart(fig, use_container_width=True)
            st.caption(
                "Substantial heterogeneity in average duration suggests uneven judicial processing efficiency across courts."
            )

        # Scatter: active_cases vs mean_duration
        size_col = "backlog" if "backlog" in perf.columns else ("resolved_cases" if "resolved_cases" in perf.columns else "active_cases")
        perf_scatter = perf.dropna(subset=["active_cases", "mean_duration"]).copy()
        if not perf_scatter.empty:
            # efficiency category
            if "efficiency_category" in perf_scatter.columns:
                color_col = "efficiency_category"
            else:
                median_dur = perf_scatter["mean_duration"].median()
                perf_scatter["efficiency_category"] = np.where(perf_scatter["mean_duration"] > median_dur, "High duration", "Low duration")
                color_col = "efficiency_category"
            color_map = {"High duration": COLORS["duration"], "Low duration": COLORS["active"]}

            # size scaling (sqrt) and clipping for readability
            size_vals = perf_scatter.get(size_col, perf_scatter['active_cases']).fillna(0).astype(float)
            size_scaled = np.sqrt(size_vals + 1)
            # normalize to 6..36
            smin, smax = size_scaled.min(), size_scaled.max()
            if smax > smin:
                size_norm = 6 + (size_scaled - smin) / (smax - smin) * 30
            else:
                size_norm = np.clip(size_scaled, 6, 36)
            perf_scatter['_marker_size'] = size_norm

            fig = px.scatter(
                perf_scatter,
                x="active_cases",
                y="mean_duration",
                size="_marker_size",
                size_max=36,
                color=color_col,
                color_discrete_map=color_map,
                hover_data={"court_id": True, "active_cases": True, "mean_duration": True, size_col: True},
                title="Court workload vs duration",
            )
            # visual tuning
            fig.update_traces(marker=dict(opacity=0.65, line=dict(width=0.5, color="rgba(0,0,0,0.15)")))

            # quadrant lines: median; use capped axis ranges to avoid extreme outliers collapsing plot
            median_active = perf_scatter["active_cases"].median()
            median_dur = perf_scatter["mean_duration"].median()
            xcap = perf_scatter["active_cases"].quantile(0.98) * 1.1
            ycap = perf_scatter["mean_duration"].quantile(0.98) * 1.1
            fig.add_shape(type="line", x0=median_active, x1=median_active, y0=0, y1=ycap, line=dict(dash="dash", color="#666"))
            fig.add_shape(type="line", x0=0, x1=xcap, y0=median_dur, y1=median_dur, line=dict(dash="dash", color="#666"))

            # use log x-axis if heavily skewed
            if perf_scatter["active_cases"].max() > 10000:
                fig.update_xaxes(type="log")

            fig = apply_common_layout(fig, height=420, title="Court workload vs resolution duration")
            fig.update_xaxes(title_text="Active cases")
            fig.update_yaxes(title_text="Mean duration (days)")

            # label key outliers: top backlog and top duration
            try:
                labels = pd.concat([
                    perf_scatter.nlargest(3, size_col),
                    perf_scatter.nlargest(3, "mean_duration"),
                ]).drop_duplicates()
                for _, r in labels.iterrows():
                    fig.add_annotation(x=r["active_cases"], y=r["mean_duration"], text=r.get("court_id", ""), showarrow=True, ax=10, ay=-10, font=dict(size=10))
            except Exception:
                pass

            st.plotly_chart(fig, use_container_width=True)
            st.caption(
                "Courts combining high workload and long average durations may indicate localized congestion or limited resolution capacity."
            )

        st.subheader("Court performance table")
        display_cols = [
        "court_id",
        "active_cases",
        "resolved_cases",
        "mean_duration",
        "median_duration",
        "backlog"
        ]

        display_cols = [
            c for c in display_cols
            if c in perf.columns
        ]

        st.dataframe(
            perf[display_cols],
            use_container_width=True
        )


# =============================================================================
# Duration analysis
# =============================================================================


elif page == "Duration Analysis":

    section("Case duration analysis", "Distributional analysis of judicial resolution times under right-censoring.")

    if case_metrics.empty:
        st.info("Case-level metrics not available.")
    else:
        # prepare durations
        cm = case_metrics.copy()
        cm = cm[cm["duration_days"].notna()]
        cm["log_duration"] = np.log1p(cm["duration_days"].clip(lower=0))

        # Histogram of log-duration (compact)
        median_log = cm["log_duration"].median()
        fig = px.histogram(cm, x="log_duration", nbins=30, color_discrete_sequence=[COLORS["duration"]], title="Log-transformed distribution of durations (log1p)")
        fig = apply_common_layout(fig, height=360)
        fig.update_layout(showlegend=False)
        fig.update_xaxes(title_text="log1p(duration_days)")
        # median marker
        fig.add_shape(type="line", x0=median_log, x1=median_log, y0=0, y1=1, yref="paper", line=dict(dash="dash", color="#444"))
        fig.add_annotation(x=median_log, y=0.98, yref="paper", text="median", showarrow=False, font=dict(size=10))
        st.plotly_chart(fig, use_container_width=True)

        st.caption("Right-censoring likely biases recent duration estimates downward.")

        # ECDF (step)
        ecdf_df = cm.sort_values("log_duration")["log_duration"].reset_index(drop=True)
        ecdf = pd.DataFrame({"x": ecdf_df, "ecdf": (np.arange(len(ecdf_df)) + 1) / len(ecdf_df)})
        fig = px.line(ecdf, x="x", y="ecdf", title="Cumulative distribution of case durations", color_discrete_sequence=[COLORS["duration"]])
        fig = apply_common_layout(fig, height=320)
        fig.update_layout(showlegend=False)
        fig.update_xaxes(title_text="log1p(duration_days)")
        fig.update_yaxes(title_text="Fraction ≤ x")
        st.plotly_chart(fig, use_container_width=True)

        # Boxplot (log durations) compact
        fig = go.Figure()
        fig.add_trace(
            go.Box(
                y=cm["log_duration"],
                boxpoints=False,
                marker=dict(color=COLORS["duration"]),
                name="log_duration",
            )
        )
        fig = apply_common_layout(fig, height=220)
        fig.update_yaxes(range=[0, 8])
        st.plotly_chart(fig, use_container_width=True)

        # Concise methodological note
        st.caption(
            "Recent unresolved cases may bias observed duration estimates downward."
        )

        # Kaplan-Meier if lifelines is available
        try:
            from lifelines import KaplanMeierFitter

            st.subheader("Kaplan–Meier survival estimate (termination)")
            # event_observed = terminated (True if terminated)
            if "is_active" in cm.columns:
                durations = cm["duration_days"].clip(lower=0)
                event_observed = (~cm["is_active"]).astype(int)
                kmf = KaplanMeierFitter()
                kmf.fit(durations, event_observed=event_observed, label="All cases")
                km_df = kmf.survival_function_.reset_index()
                fig = px.line(km_df, x=km_df.columns[0], y="KM_estimate" if "KM_estimate" in km_df.columns else km_df.columns[1], title="Kaplan-Meier survival curve")
                fig = apply_common_layout(fig, height=420)
                fig.update_xaxes(title_text="Duration days")
                fig.update_yaxes(title_text="Survival probability")
                st.plotly_chart(fig, use_container_width=True)
                st.caption("Survival curve: probability a case remains unresolved beyond t days. Censoring handled by KM estimator.")
            else:
                st.info("Kaplan–Meier requires `is_active` column in case metrics.")
        except Exception:
            st.caption(
                "Survival-analysis estimates are currently unavailable in this environment."
            )


# =============================================================================
# Raw tables
# =============================================================================


elif page == "Raw Tables":

    section("Raw analytical tables", "Direct access to Gold layer outputs.")

    table_choice = st.selectbox("Choose table", ["backlog", "clearance", "court_performance", "case_metrics"])

    table_map = {
        "backlog": backlog,
        "clearance": clearance,
        "court_performance": performance,
        "case_metrics": case_metrics,
    }

    df = table_map.get(table_choice, pd.DataFrame()).copy()

    if df.empty:
        st.info("Selected table is empty or not available.")
    else:
        # simple text filter across string columns
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
- **Silver layer** → cleaned, standardized, and validated judicial data,
- **Gold layer** → aggregated analytical indicators used for backlog, duration, and court-performance analytics.

### Methodological notes

Several indicators should be interpreted cautiously:

- many recent cases remain unresolved (right-censoring),
- historical resolution records are incomplete for some years,
- duration statistics primarily reflect resolved cases,
- clearance indicators may be unstable during sparse-resolution periods.

The dashboard is intended as an analytical observatory of judicial workload dynamics rather than a deterministic performance evaluation tool.
"""
    )

    ck_info = load_checkpoint_info()
    layer_sizes = get_layer_sizes()

    st.caption(
        f"Latest checkpoint: {ck_info.get('dockets', ck_info)}"
    )

    st.caption(
        f"Bronze files: {layer_sizes['bronze']['files']} | "
        f"Silver files: {layer_sizes['silver']['files']} | "
        f"Gold files: {layer_sizes['gold']['files']}"
    )
