"""
Gold analytical case metrics table.

This script creates an enriched analytical dataset
from the Silver docket dataset, retaining only the most recent
entry for each distinct case_name based on date_modified.
"""

import duckdb
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

output_file = GOLD_PATH / "case_metrics.parquet"
output_file.parent.mkdir(parents=True, exist_ok=True)

# ============================================================
# DUCKDB CONNECTION
# ============================================================

print("Connecting to DuckDB...")
con = duckdb.connect()

# ============================================================
# BUILD ANALYTICAL TABLE WITH DEDUPLICATION
# ============================================================

print("Building case metrics dataset...")

query = f"""
WITH raw_silver_data AS (
    SELECT 
        id, 
        court_id, 
        case_name, 
        nature_of_suit, 
        jurisdiction_type, 
        cause, 
        blocked, 
        source, 
        is_appeal,
        quarter_filed, 
        quarter_terminated,
        docket_number,
        jury_demand,
        
        -- FIX: Cast ISO text strings to explicit DATE types for math operations
        TRY_CAST(date_filed AS DATE) AS date_filed,
        TRY_CAST(date_terminated AS DATE) AS date_terminated,
        TRY_CAST(date_last_filing AS DATE) AS date_last_filing,
        
        -- Try to cast timestamp metadata cleanly
        TRY_CAST(date_modified AS TIMESTAMP) AS date_modified
        
    FROM read_parquet('{silver_files}', union_by_name=True)
),
ranked_cases AS (
    SELECT
        id, court_id, case_name, nature_of_suit, jurisdiction_type, cause, blocked, source, is_appeal,
        date_filed, date_terminated, date_last_filing, date_modified,
        quarter_filed, quarter_terminated,jury_demand,

        CASE
            WHEN date_terminated IS NULL THEN TRUE
            ELSE FALSE
        END AS is_active,

        -- This will now execute perfectly since arguments are true DATE objects
        CASE
            WHEN date_filed IS NOT NULL AND date_terminated IS NOT NULL
            THEN date_diff('day', date_filed, date_terminated)
            ELSE NULL
        END AS duration_days,

        CASE
            WHEN date_filed IS NOT NULL THEN year(date_filed)
            ELSE NULL
        END AS year_filed,

        CASE
            WHEN date_terminated IS NOT NULL THEN year(date_terminated)
            ELSE NULL
        END AS year_terminated,

        CASE
            WHEN quarter_terminated IS NOT NULL AND quarter_terminated != 'q0' THEN
                CAST(year(date_terminated) AS VARCHAR) || '-' || quarter_terminated
            ELSE NULL
        END AS year_quarter_terminated,

        CASE
            WHEN quarter_filed IS NOT NULL AND quarter_filed != 'q0' THEN
                CAST(year(date_filed) AS VARCHAR) || '-' || quarter_filed
            ELSE NULL
        END AS year_quarter_filed,

        ROW_NUMBER() OVER (
            PARTITION BY docket_number 
            ORDER BY date_modified DESC, id DESC
        ) AS row_num

    FROM raw_silver_data
)
SELECT 
    id, court_id, case_name, date_filed, date_terminated, date_last_filing,
    nature_of_suit, jurisdiction_type, cause, blocked, source, 
    quarter_filed, quarter_terminated, is_appeal, date_modified,
    is_active, duration_days, year_filed, year_terminated,
    year_quarter_terminated, year_quarter_filed, jury_demand,
FROM ranked_cases
WHERE row_num = 1
"""

df = con.execute(query).df()

# ============================================================
# EXPORT GOLD TABLE
# ============================================================

df.to_parquet(
    output_file,
    index=False
)

print("\nCase metrics table successfully created.")
print(f"\nOutput file : {output_file}")

print("\nDataset overview:")
print(df.info())

print("\nPreview:")
print(df.head())