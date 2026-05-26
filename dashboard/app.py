from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st
import json
import os



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
# Helpers
# =============================================================================

def section(title: str, intro: str | None = None):
    st.divider()
    st.header(title)

    if intro:
        st.markdown(intro)


def load_checkpoint_info():
    ck = Path(__file__).resolve().parent.parent / "logs" / "checkpoint.json"
    if ck.exists():
        try:
            return json.load(open(ck, "r", encoding="utf-8"))
        except Exception:
            return {}
    return {}


def get_layer_sizes():
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


@st.cache_resource
def get_connection():
    return duckdb.connect()


@st.cache_data
def load_backlog():
    return pd.read_parquet(
        GOLD_DIR / "backlog_by_year.parquet"
    )


@st.cache_data
def load_clearance():
    return pd.read_parquet(
        GOLD_DIR / "clearance_rate_by_year.parquet"
    )


@st.cache_data
def load_court_performance():
    return pd.read_parquet(
        GOLD_DIR / "court_performance_metrics.parquet"
    )


@st.cache_data
def load_case_metrics():
    return pd.read_parquet(
        GOLD_DIR / "case_metrics.parquet"
    )


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
# Load data
# =============================================================================

backlog = load_backlog()
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
        "Raw Tables"
    ]
)

top_n = st.sidebar.slider(
    "Top courts",
    min_value=5,
    max_value=50,
    value=20
)

# temporal filters
years = sorted(backlog["year"].unique())
min_year, max_year = int(years[0]), int(years[-1])
year_range = st.sidebar.slider("Year range", min_value=min_year, max_value=max_year, value=(min_year, max_year))

# court type filter (if available)
court_types = []
if "jurisdiction_type" in case_metrics.columns:
    court_types = sorted(case_metrics["jurisdiction_type"].dropna().unique())
selected_court_types = st.sidebar.multiselect("Court types", options=court_types, default=court_types)

# active/resolved filter
show_active = st.sidebar.checkbox("Show active cases", value=True)
show_resolved = st.sidebar.checkbox("Show resolved cases", value=True)


# =============================================================================
# Main title
# =============================================================================

st.title("Judicial Analytics Dashboard")

st.caption(
    "Court workload, backlog, clearance rate, and duration analytics."
)


# =============================================================================
# Overview
# =============================================================================

if page == "Overview":

    section(
        "System overview",
        "Main judicial KPIs extracted from the Gold analytics layer."
    )

    total_cases = len(case_metrics)

    active_cases = int(
        performance["active_cases"].sum()
    )

    resolved_cases = int(
        performance["resolved_cases"].sum()
    )

    avg_duration = round(
        performance["mean_duration"]
        .replace(0, pd.NA)
        .dropna()
        .mean(),
        2
    )

    # latest backlog within selected year range
    latest_backlog = int(
        backlog_enh.loc[backlog_enh["year"].between(year_range[0], year_range[1]), "backlog"].iloc[-1]
    )

    latest_clearance = round(
        clearance["clearance_rate_pct"]
        .dropna()
        .iloc[-1],
        2
    )

    # -------------------------------------------------------------------------
    # KPI cards
    # -------------------------------------------------------------------------

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Total cases",
            total_cases
        )

    with col2:
        st.metric(
            "Active cases",
            active_cases
        )

    with col3:
        st.metric(
            "Resolved cases",
            resolved_cases
        )

    col4, col5, col6 = st.columns(3)

    with col4:
        st.metric(
            "Avg duration (days)",
            avg_duration
        )

    with col5:
        st.metric(
            "Current backlog",
            latest_backlog
        )

    with col6:
        st.metric(
            "Clearance rate %",
            latest_clearance
        )

    # -------------------------------------------------------------------------
    # Monitoring info
    # -------------------------------------------------------------------------
    ck_info = load_checkpoint_info()
    layer_sizes = get_layer_sizes()

    st.subheader("Data & ingestion status")
    st.write(f"Latest checkpoint: {ck_info.get('dockets', ck_info)}")
    st.write(f"Bronze files: {layer_sizes['bronze']['files']}, Silver files: {layer_sizes['silver']['files']}, Gold files: {layer_sizes['gold']['files']}")

    # -------------------------------------------------------------------------
    # Charts
    # -------------------------------------------------------------------------

    col1, col2 = st.columns(2)

    # -------------------------------------------------------------------------
    # Backlog
    # -------------------------------------------------------------------------

    with col1:

        st.subheader("Backlog evolution")

        df_plot = backlog_enh[backlog_enh["year"].between(year_range[0], year_range[1])]
        fig = px.bar(
            df_plot,
            x="year",
            y="backlog",
            color="backlog",
            title="Judicial backlog over time"
        )

        fig.update_layout(
            template="plotly_white",
            height=450,
            showlegend=False
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

    # -------------------------------------------------------------------------
    # Inflow / Outflow
    # -------------------------------------------------------------------------

    with col2:

        st.subheader("Inflow vs outflow")

        flow_df = backlog_enh.loc[backlog_enh["year"].between(year_range[0], year_range[1]), [
            "year",
            "inflow",
            "outflow"
        ]].melt(
            id_vars="year",
            var_name="flow_type",
            value_name="cases"
        )

        fig = px.bar(
            flow_df,
            x="year",
            y="cases",
            color="flow_type",
            barmode="group",
            title="Case inflow and outflow"
        )

        fig.update_layout(
            template="plotly_white",
            height=450
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

    # -------------------------------------------------------------------------
    # Pie chart
    # -------------------------------------------------------------------------

    st.subheader("Active vs resolved cases")

    status_df = pd.DataFrame({
        "status": ["Active", "Resolved"],
        "cases": [active_cases, resolved_cases]
    })

    fig = px.pie(
        status_df,
        names="status",
        values="cases",
        title="Case status distribution"
    )

    fig.update_layout(
        template="plotly_white",
        height=500
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )


# =============================================================================
# Backlog analytics
# =============================================================================

elif page == "Backlog Analytics":

    section(
        "Backlog and clearance rate",
        "Temporal congestion indicators."
    )

    fig = px.bar(
        backlog,
        x="year",
        y="backlog",
        title="Backlog by year"
    )

    fig.update_layout(
        template="plotly_white",
        height=500
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )

    # -------------------------------------------------------------------------

    clearance_clean = clearance.dropna(
        subset=["clearance_rate_pct"]
    )

    fig = px.line(
        clearance_clean,
        x="year",
        y="clearance_rate_pct",
        markers=True,
        title="Clearance rate (%)"
    )

    fig.update_layout(
        template="plotly_white",
        height=500
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )


# =============================================================================
# Court performance
# =============================================================================

elif page == "Court Performance":

    section(
        "Court workload and efficiency",
        "Court-level performance indicators."
    )

    top_active = performance.sort_values(
        by="active_cases",
        ascending=False
    ).head(top_n)

    fig = px.bar(
        top_active,
        x="court_id",
        y="active_cases",
        color="active_cases",
        title="Most active courts"
    )

    fig.update_layout(
        template="plotly_white",
        height=600
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )

    # -------------------------------------------------------------------------

    duration_clean = performance[
        performance["mean_duration"] > 0
    ]

    fig = px.bar(
        duration_clean.sort_values(
            by="mean_duration",
            ascending=False
        ).head(top_n),
        x="court_id",
        y="mean_duration",
        color="mean_duration",
        title="Average case duration by court"
    )

    fig.update_layout(
        template="plotly_white",
        height=600
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )

    # -------------------------------------------------------------------------

    st.subheader("Court performance table")

    st.dataframe(
        performance,
        use_container_width=True
    )


# =============================================================================
# Duration analysis
# =============================================================================

elif page == "Duration Analysis":

    section(
        "Case duration analysis",
        "Distribution of judicial resolution times."
    )

    resolved = case_metrics[
        case_metrics["duration_days"].notna()
    ]

    fig = px.histogram(
        resolved,
        x="duration_days",
        nbins=30,
        title="Distribution of case durations"
    )

    fig.update_layout(
        template="plotly_white",
        height=600
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )

    # -------------------------------------------------------------------------

    fig = px.box(
        resolved,
        y="duration_days",
        title="Case duration boxplot"
    )

    fig.update_layout(
        template="plotly_white",
        height=600
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )

    # -------------------------
    # Duration quantiles and censoring warnings
    # -------------------------
    if not duration_quantiles.empty:
        dq_sel = duration_quantiles.loc[duration_quantiles["year"].between(year_range[0], year_range[1])]

        if dq_sel["sparse_year_warning"].any():
            st.warning("Some years in the selected range have low termination counts relative to inflow — interpret duration statistics with caution.")

        st.subheader("Duration quantiles by year")
        st.dataframe(dq_sel, use_container_width=True)


# =============================================================================
# Raw tables
# =============================================================================

elif page == "Raw Tables":

    section(
        "Raw analytical tables",
        "Direct access to Gold layer outputs."
    )

    table_choice = st.selectbox(
        "Choose table",
        [
            "backlog",
            "clearance",
            "court_performance",
            "case_metrics"
        ]
    )

    if table_choice == "backlog":
        st.dataframe(
            backlog,
            use_container_width=True
        )

    elif table_choice == "clearance":
        st.dataframe(
            clearance,
            use_container_width=True
        )

    elif table_choice == "court_performance":
        st.dataframe(
            performance,
            use_container_width=True
        )

    elif table_choice == "case_metrics":
        st.dataframe(
            case_metrics,
            use_container_width=True
        )


# =============================================================================
# Footer
# =============================================================================

st.divider()

st.caption(
    "Medallion architecture: Bronze → Silver → Gold → Analytics Dashboard"
)