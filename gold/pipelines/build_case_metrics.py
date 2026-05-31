"""
Gold analytical case metrics table.

This script creates an enriched analytical dataset
from the Silver docket dataset, retaining only the most recent
entry for each distinct docket_number based on date_modified,
and enriches it with structural/geographical court classification metadata.
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
# PATHS & CONFIGURATION
# ============================================================

silver_files = (Path(SILVER_PATH) / "*.parquet").as_posix()

output_file = GOLD_PATH / "case_metrics.parquet"
output_file.parent.mkdir(parents=True, exist_ok=True)

# Locate the court classification metadata file
courts_file = PROJECT_ROOT / "silver" / "courts" / "courts_classified.parquet"
if not courts_file.exists():
    # Fallback to look directly in the current working directory if paths differ
    if Path("courts_classified.parquet").exists():
        courts_file = Path("courts_classified.parquet")
    else:
        raise FileNotFoundError(
            f"Could not locate 'courts_classified.parquet' at {courts_file.as_posix()} "
            "or in the current working directory."
        )

# ============================================================
# DUCKDB CONNECTION
# ============================================================

print("Connecting to DuckDB...")
con = duckdb.connect()

# ============================================================
# BUILD ANALYTICAL TABLE WITH DEDUPLICATION & COURT METADATA JOIN
# ============================================================

print("Building case metrics dataset enriched with court metadata...")

query = f"""
WITH raw_silver_data AS (
    SELECT 
        id, 
        court_id, 
        case_name, 
        nature_of_suit, 
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
        id, court_id, case_name, nature_of_suit, cause, blocked, source, is_appeal,
        date_filed, date_terminated, date_last_filing, date_modified,
        quarter_filed, quarter_terminated, jury_demand,

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
    r.id, r.court_id, r.case_name, r.date_filed, r.date_terminated, r.date_last_filing,
    r.nature_of_suit, r.cause, r.blocked, r.source, 
    r.quarter_filed, r.quarter_terminated, r.is_appeal, r.date_modified,
    r.is_active, r.duration_days, r.year_filed, r.year_terminated,
    r.year_quarter_terminated, r.year_quarter_filed, r.jury_demand,
    
    -- Enriched structural features from court classification
    c.circuit,
    c.level,
    c.is_federal,
    c.jurisdiction,
    c.state,
FROM ranked_cases r
LEFT JOIN read_parquet('{courts_file.as_posix()}') c
  ON r.court_id = c.court_id
WHERE r.row_num = 1
"""

df = con.execute(query).df()

# ============================================================
# EXPORT GOLD TABLE
# ============================================================

df.to_parquet(
    output_file,
    index=False
)

print("\nCase metrics table successfully created and enriched with court classification.")
print(f"Output file : {output_file}")

print("\nDataset overview:")
print(df.info())

print("\nPreview:")
print(df.head())