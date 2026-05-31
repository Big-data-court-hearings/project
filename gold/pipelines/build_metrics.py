"""
Gold layer metrics pipeline.

This script:
- loads Silver parquet data
- creates analytical KPIs with DuckDB
- exports Gold metrics datasets
"""

import duckdb
import pandas as pd

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

sys.path.append(str(PROJECT_ROOT))

from ingestion.config import (
    SILVER_PATH,
    GOLD_PATH
)

# ============================================================
# PATHS
# ============================================================

silver_files = (Path(SILVER_PATH) / "*.parquet").as_posix()

active_cases_file = GOLD_PATH / "active_cases_by_court.parquet"

resolution_time_file = GOLD_PATH / "avg_resolution_time_by_court.parquet"

# New Export Path for Circuit Metrics
circuit_metrics_file = GOLD_PATH / "metrics_by_circuit.parquet"

# ============================================================
# CONNECT TO DUCKDB
# ============================================================

print("Connecting to DuckDB...")

con = duckdb.connect()

# ============================================================
# LOAD SILVER DATA
# ============================================================

print("Loading Silver parquet dataset...")

query = f"""
SELECT *
FROM read_parquet('{silver_files}')
"""

df = con.execute(query).df()

print(f"Loaded {len(df)} rows")

# ============================================================
# REGISTER TABLE
# ============================================================

con.register("dockets", df)

# ============================================================
# KPI 1 : ACTIVE CASES BY COURT
# ============================================================

print("Building active case metrics...")

active_cases_query = """
SELECT
    court_id,
    COUNT(*) AS active_cases
FROM dockets
WHERE date_terminated IS NULL
GROUP BY court_id
ORDER BY active_cases DESC
"""

active_cases_df = con.execute(
    active_cases_query
).df()

# ============================================================
# EXPORT KPI 1
# ============================================================

active_cases_df.to_parquet(
    active_cases_file,
    index=False
)

print("\nActive cases KPI exported.")

# ============================================================
# KPI 2 : AVERAGE RESOLUTION TIME BY COURT
# ============================================================

print("Building resolution time metrics...")

resolution_query = """
SELECT
    court_id,

    AVG(
        date_diff(
            'day',
            date_filed,
            date_terminated
        )
    ) AS avg_resolution_days

FROM dockets

WHERE
    date_filed IS NOT NULL
    AND date_terminated IS NOT NULL

GROUP BY court_id

ORDER BY avg_resolution_days DESC
"""

resolution_df = con.execute(
    resolution_query
).df()

# ============================================================
# EXPORT KPI 2
# ============================================================

resolution_df.to_parquet(
    resolution_time_file,
    index=False
)

print("\nResolution time KPI exported.")

# ============================================================
# KPI 3 : METRICS BY CIRCUIT (Active and Resolution combined)
# ============================================================

print("Building metrics grouped by circuit...")

circuit_query = """
SELECT
    circuit,
    
    -- Count of cases where date_terminated is null
    COUNT(CASE WHEN date_terminated IS NULL THEN 1 END) AS active_cases,
    
    -- Average resolution days for closed cases
    AVG(
        CASE 
            WHEN date_filed IS NOT NULL AND date_terminated IS NOT NULL 
            THEN date_diff('day', date_filed, date_terminated)
        END
    ) AS avg_resolution_days

FROM dockets

WHERE circuit IS NOT NULL

GROUP BY circuit

ORDER BY active_cases DESC
"""

circuit_df = con.execute(
    circuit_query
).df()

# ============================================================
# EXPORT KPI 3
# ============================================================

circuit_df.to_parquet(
    circuit_metrics_file,
    index=False
)

print("\nCircuit metrics KPI exported.")

# ============================================================
# FINAL OUTPUT
# ============================================================

print("\nGold metrics successfully created.")

print("\n=== ACTIVE CASES BY COURT ===")
print(active_cases_df.head())

print("\n=== RESOLUTION TIME BY COURT ===")
print(resolution_df.head())

print("\n=== METRICS BY CIRCUIT ===")
print(circuit_df.head())