"""
Temporal analytics metrics pipeline.

This script creates a comprehensive court performance time-series dataset including:
- Quarterly case inflow metrics (by court_id)
- Quarterly case outflow metrics (by court_id)
- Backlog clearance ratio (Outflow / Inflow) mapped from q1-2023 to q1-2026
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
backlog_evolution_file = GOLD_PATH / "court_backlog_evolution.parquet"

# Ensure output directory exists
backlog_evolution_file.parent.mkdir(parents=True, exist_ok=True)

# ============================================================
# CONNECT TO DUCKDB
# ============================================================
print("Connecting to DuckDB...")
con = duckdb.connect()

# ============================================================
# KPI : DYNAMIC QUARTERLY INFLOW, OUTFLOW & BACKLOG RATIO
# ============================================================
print("Building court quarterly backlog evolution metrics...")

# We use subqueries to safely calculate quarterly aggregates, 
# then join them using a FULL JOIN to avoid losing periods where a 
# court might have had 0 active filings or 0 resolutions.
query = f"""
COPY (
    WITH quarterly_inflow AS (
        SELECT
            court_id,
            year_quarter_filed AS year_quarter,
            COUNT(*) AS filed_cases
        FROM read_parquet('{case_metrics_file}')
        WHERE year_quarter_filed IS NOT NULL 
          AND year_quarter_filed IN (
              '2023-q1', '2023-q2', '2023-q3', '2023-q4',
              '2024-q1', '2024-q2', '2024-q3', '2024-q4',
              '2025-q1', '2025-q2', '2025-q3', '2025-q4',
              '2026-q1'
          )
        GROUP BY court_id, year_quarter_filed
    ),
    quarterly_outflow AS (
        SELECT
            court_id,
            year_quarter_terminated AS year_quarter,
            COUNT(*) AS terminated_cases
        FROM read_parquet('{case_metrics_file}')
        WHERE year_quarter_terminated IS NOT NULL 
          AND year_quarter_terminated IN (
              '2023-q1', '2023-q2', '2023-q3', '2023-q4',
              '2024-q1', '2024-q2', '2024-q3', '2024-q4',
              '2025-q1', '2025-q2', '2025-q3', '2025-q4',
              '2026-q1'
          )
        GROUP BY court_id, year_quarter_terminated
    )
    SELECT
        COALESCE(i.court_id, o.court_id) AS court_id,
        COALESCE(i.year_quarter, o.year_quarter) AS year_quarter,
        COALESCE(i.filed_cases, 0) AS inflow_cases,
        COALESCE(o.terminated_cases, 0) AS outflow_cases,
        
        -- Backlog Clearance Ratio Calculation (Outflow / Inflow)
        -- If inflow is 0, we output NULL (or 0.0) to prevent a division-by-zero crash
        CASE 
            WHEN COALESCE(i.filed_cases, 0) > 0 
            THEN ROUND(CAST(COALESCE(o.terminated_cases, 0) AS DOUBLE) / i.filed_cases, 4)
            ELSE NULL 
        END AS backlog_clearance_ratio

    FROM quarterly_inflow i
    FULL OUTER JOIN quarterly_outflow o
        ON i.court_id = o.court_id 
       AND i.year_quarter = o.year_quarter
    ORDER BY court_id ASC, year_quarter ASC
) TO '{backlog_evolution_file.as_posix()}' (FORMAT 'PARQUET', CODEC 'SNAPPY');
"""

con.execute(query)
print("Backlog evolution dataset generated and exported.")

# ============================================================
# FINAL OUTPUT PREVIEW
# ============================================================
df_preview = con.execute(f"SELECT * FROM read_parquet('{backlog_evolution_file.as_posix()}') LIMIT 20").df()

print("\n=== QUARTERLY METRICS METRICS VIEW (FIRST 20 ROWS) ===")
print(df_preview)