"""
Advanced Gold metrics for judicial analytics.

Produces:
- backlog_enhanced.parquet (rolling averages, yoy growth)
- duration_quantiles_by_year.parquet (median, p90, p95 per year)
- court_year_trends.parquet (inflow/outflow/backlog per court-year)
- active_resolved_evolution.parquet (per-year active/resolved counts)

Uses DuckDB for scalable aggregation over parquet inputs.
"""
import duckdb
import pandas as pd
import numpy as np
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

sys.path.append(str(PROJECT_ROOT))

from ingestion.config import GOLD_PATH


case_metrics_file = GOLD_PATH / "case_metrics.parquet"
backlog_file = GOLD_PATH / "backlog_by_year.parquet"

OUT_BACKLOG = GOLD_PATH / "backlog_enhanced.parquet"
OUT_DURATION_YEAR = GOLD_PATH / "duration_quantiles_by_year.parquet"
OUT_COURT_YEAR = GOLD_PATH / "court_year_trends.parquet"
OUT_ACTIVE_RESOLVED = GOLD_PATH / "active_resolved_evolution.parquet"


def main():
    print("Connecting to DuckDB...")
    con = duckdb.connect()

    print("Loading case metrics and backlog...")
    con.register("cases", con.execute(f"SELECT * FROM read_parquet('{case_metrics_file}')").df())
    backlog_df = pd.read_parquet(backlog_file)

    # -------------------------
    # Backlog enhancements
    # -------------------------
    print("Computing backlog rolling averages and YoY growth...")

    b = backlog_df.sort_values("year").copy()
    b["rolling_backlog_3y"] = b["backlog"].rolling(window=3, min_periods=1).mean()
    b["backlog_yoy_change"] = b["backlog"].pct_change().replace([np.inf, -np.inf], np.nan)

    b.to_parquet(OUT_BACKLOG, index=False)
    print(f"Wrote {OUT_BACKLOG}")

    # -------------------------
    # Duration quantiles by year
    # -------------------------
    print("Computing duration quantiles by year...")

    # Use DuckDB to aggregate efficiently
    duration_query = f"""
    SELECT
        year_terminated AS year,
        COUNT(duration_days) AS terminated_count,
        AVG(duration_days) AS mean_duration,
        quantile(duration_days, 0.5) AS median_duration,
        quantile(duration_days, 0.90) AS p90_duration,
        quantile(duration_days, 0.95) AS p95_duration
    FROM read_parquet('{case_metrics_file}')
    WHERE duration_days IS NOT NULL
    GROUP BY year_terminated
    ORDER BY year_terminated
    """

    dq = con.execute(duration_query).df()

    # join with inflow/outflow to identify sparse years
    inflow = pd.read_parquet(GOLD_PATH / "case_inflow_by_year.parquet").rename(columns={"year_filed":"year","filed_cases":"inflow"})
    outflow = pd.read_parquet(GOLD_PATH / "case_outflow_by_year.parquet").rename(columns={"year_terminated":"year","terminated_cases":"outflow"})

    dq = dq.merge(inflow, on="year", how="left").merge(outflow, on="year", how="left")
    dq["inflow"] = dq["inflow"].fillna(0)
    dq["terminated_count"] = dq["terminated_count"].fillna(0)

    # flag sparse years where terminated << inflow (e.g., less than 20%)
    dq["sparse_year_warning"] = dq.apply(lambda r: True if r["inflow"]>0 and r["terminated_count"] / r["inflow"] < 0.2 else False, axis=1)

    dq.to_parquet(OUT_DURATION_YEAR, index=False)
    print(f"Wrote {OUT_DURATION_YEAR}")

    # -------------------------
    # Court-year trends: inflow/outflow/backlog per court-year
    # -------------------------
    print("Computing court-year trends...")

    court_inflow_q = f"""
    SELECT court_id, year_filed AS year, COUNT(*) AS inflow
    FROM read_parquet('{case_metrics_file}')
    WHERE year_filed IS NOT NULL
    GROUP BY court_id, year_filed
    """

    court_outflow_q = f"""
    SELECT court_id, year_terminated AS year, COUNT(*) AS outflow
    FROM read_parquet('{case_metrics_file}')
    WHERE year_terminated IS NOT NULL
    GROUP BY court_id, year_terminated
    """

    inflow_df = con.execute(court_inflow_q).df()
    outflow_df = con.execute(court_outflow_q).df()

    # combine and compute rolling 3-year averages per court
    cy = pd.merge(inflow_df, outflow_df, on=["court_id","year"], how="outer").fillna(0)
    cy = cy.sort_values(["court_id","year"]).reset_index(drop=True)
    cy["cumulative_inflow"] = cy.groupby("court_id")["inflow"].cumsum()
    cy["cumulative_outflow"] = cy.groupby("court_id")["outflow"].cumsum()
    cy["backlog_end_of_year"] = cy["cumulative_inflow"] - cy["cumulative_outflow"]
    cy["rolling_inflow_3y"] = cy.groupby("court_id")["inflow"].rolling(3, min_periods=1).mean().reset_index(0,drop=True)
    cy["rolling_outflow_3y"] = cy.groupby("court_id")["outflow"].rolling(3, min_periods=1).mean().reset_index(0,drop=True)

    cy.to_parquet(OUT_COURT_YEAR, index=False)
    print(f"Wrote {OUT_COURT_YEAR}")

    # -------------------------
    # Active vs resolved evolution
    # Use backlog cumulative and cumulative outflow
    # -------------------------
    print("Computing active vs resolved evolution...")

    overall = backlog_df.sort_values("year").copy()
    overall["cumulative_inflow"] = overall["inflow"].cumsum()
    overall["cumulative_outflow"] = overall["outflow"].cumsum()
    overall["active_end_of_year"] = overall["backlog"]

    overall_out = overall[["year","inflow","outflow","cumulative_inflow","cumulative_outflow","backlog","active_end_of_year"]]
    overall_out.to_parquet(OUT_ACTIVE_RESOLVED, index=False)
    print(f"Wrote {OUT_ACTIVE_RESOLVED}")

    print("Advanced metrics built successfully.")


if __name__ == '__main__':
    main()
