"""
Temporal analytics metrics pipeline.

This script creates:
- case inflow metrics
- case outflow metrics
- backlog evolution metrics
"""

import duckdb

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

sys.path.append(str(PROJECT_ROOT))

from ingestion.config import GOLD_PATH

# ============================================================
# PATHS
# ============================================================

case_metrics_file = GOLD_PATH / "case_metrics.parquet"

inflow_file = GOLD_PATH / "case_inflow_by_year.parquet"

outflow_file = GOLD_PATH / "case_outflow_by_year.parquet"

# ============================================================
# CONNECT TO DUCKDB
# ============================================================

print("Connecting to DuckDB...")

con = duckdb.connect()

# ============================================================
# KPI 1 : CASE INFLOW
# ============================================================

print("Building inflow metrics...")

inflow_query = f"""
SELECT
    year_filed,
    COUNT(*) AS filed_cases

FROM read_parquet('{case_metrics_file}')

WHERE year_filed > 2022

GROUP BY year_filed

ORDER BY year_filed
"""

inflow_df = con.execute(
    inflow_query
).df()

# ============================================================
# EXPORT INFLOW
# ============================================================

inflow_df.to_parquet(
    inflow_file,
    index=False
)

print("Inflow metrics exported.")

# ============================================================
# KPI 2 : CASE OUTFLOW
# ============================================================

print("Building outflow metrics...")

outflow_query = f"""
SELECT
    year_terminated,
    COUNT(*) AS terminated_cases

FROM read_parquet('{case_metrics_file}')

WHERE year_terminated IS NOT NULL

GROUP BY year_terminated

ORDER BY year_terminated
"""

outflow_df = con.execute(
    outflow_query
).df()

# ============================================================
# EXPORT OUTFLOW
# ============================================================

outflow_df.to_parquet(
    outflow_file,
    index=False
)

print("Outflow metrics exported.")

# ============================================================
# FINAL OUTPUT
# ============================================================

print("\n=== INFLOW ===")
print(inflow_df)

print("\n=== OUTFLOW ===")
print(outflow_df)