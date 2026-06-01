"""
Gold layer KPI metrics pipeline.

Produces:
- active_cases_by_court.parquet
- avg_resolution_time_by_court.parquet
- metrics_by_circuit.parquet

Longitudinal unnesting (active_cases_by_year/quarter) is handled by build_case_metrics.py.
"""

import duckdb
from pathlib import Path
from _common import SILVER_GLOB, GOLD_PATH, connect, ensure, courts_file

cf = courts_file()

active_cases_file    = ensure(GOLD_PATH / "current_active_cases_by_court.parquet")
resolution_time_file = ensure(GOLD_PATH / "avg_resolution_time_by_court.parquet")
circuit_metrics_file = ensure(GOLD_PATH / "metrics_by_circuit.parquet")

print("Connecting to DuckDB...")
con = connect()

# Join silver + courts once as a view — DuckDB streams this; nothing is pulled into Python RAM
con.execute(f"""
CREATE OR REPLACE VIEW dockets AS
SELECT d.*, c.circuit, c.level, c.is_federal, c.jurisdiction
FROM read_parquet('{SILVER_GLOB}', union_by_name=True) d
LEFT JOIN read_parquet('{cf.as_posix()}') c ON d.court_id = c.court_id
""")

# KPI 1: Active cases by court
print("Building active case metrics...")
active_df = con.execute("""
SELECT court_id, COUNT(*) AS active_cases
FROM dockets
WHERE date_terminated IS NULL
GROUP BY court_id
ORDER BY active_cases DESC
""").df()
active_df.to_parquet(active_cases_file, index=False)
print("Active cases KPI exported.")

# KPI 2: Average resolution time by court
print("Building resolution time metrics...")
resolution_df = con.execute("""
SELECT
    court_id,
    AVG(date_diff('day', TRY_CAST(date_filed AS DATE), TRY_CAST(date_terminated AS DATE))) AS avg_resolution_days
FROM dockets
WHERE date_filed IS NOT NULL AND date_terminated IS NOT NULL
GROUP BY court_id
ORDER BY avg_resolution_days DESC
""").df()
resolution_df.to_parquet(resolution_time_file, index=False)
print("Resolution time KPI exported.")

# KPI 3: Active + resolution by circuit
print("Building circuit metrics...")
circuit_df = con.execute("""
SELECT
    circuit,
    COUNT(CASE WHEN date_terminated IS NULL THEN 1 END) AS active_cases,
    AVG(CASE
        WHEN date_filed IS NOT NULL AND date_terminated IS NOT NULL
        THEN date_diff('day', TRY_CAST(date_filed AS DATE), TRY_CAST(date_terminated AS DATE))
    END) AS avg_resolution_days
FROM dockets
WHERE circuit IS NOT NULL
GROUP BY circuit
ORDER BY active_cases DESC
""").df()
circuit_df.to_parquet(circuit_metrics_file, index=False)
print("Circuit metrics KPI exported.")

print("\n=== CURRENT ACTIVE CASES BY COURT ===")
print(active_df.head())
print("\n=== RESOLUTION TIME BY COURT ===")
print(resolution_df.head())
print("\n=== METRICS BY CIRCUIT ===")
print(circuit_df.head())
