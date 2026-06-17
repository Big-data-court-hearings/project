"""
Builds and incrementally maintains the gold case_metrics table in a DuckLake catalog.
On each run, only silver records newer than the gold watermark (MAX date_modified)
are processed and upserted — new cases are inserted, updated cases are merged.
Full reprocessing only happens on the first run when the gold table does not exist yet.
"""

import duckdb
from pathlib import Path
from _common import (
    GOLD_PATH, CASE_METRICS_CTE,
    connect, ensure, courts_file, START_YEAR,
)


output_file= ensure(GOLD_PATH / "case_enhanced.parquet")
base_path    = Path(__file__).parent
SILVER_CATALOG = (base_path / ".." / "silver_catalog.ducklake").resolve()
SILVER_DATA    = (base_path / ".." / "silver" / "data").resolve()
GOLD_CATALOG   = (base_path / ".." / "gold_catalog.ducklake").resolve()
GOLD_DATA      = (base_path / ".." / "gold" / "data").resolve()

from pathlib import Path
import duckdb

def connect():
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent.parent
    
    # Define exact paths for BOTH catalogs
    SILVER_CAT_PATH = (project_root / "silver_catalog.ducklake").resolve()
    SILVER_DAT_PATH = (project_root / "silver" / "data").resolve()
    
    GOLD_CAT_PATH = (project_root / "gold_catalog.ducklake").resolve()
    GOLD_DAT_PATH = (project_root / "gold" / "data").resolve()
    
    print(f"Connecting to DuckLake Catalog at: {SILVER_CAT_PATH}")
    
    con = duckdb.connect()
    
    # Load required extension engine layers
    con.execute("INSTALL ducklake; LOAD ducklake;")
    
    # ATTACH SILVER DATABASE
    con.execute(
        f"ATTACH 'ducklake:{SILVER_CAT_PATH.as_posix()}' AS silver "
        f"(DATA_PATH '{SILVER_DAT_PATH.as_posix()}', OVERRIDE_DATA_PATH TRUE)"
    )
    
    # ATTACH GOLD DATABASE (Missing piece!)
    con.execute(
        f"ATTACH 'ducklake:{GOLD_CAT_PATH.as_posix()}' AS gold "
        f"(DATA_PATH '{GOLD_DAT_PATH.as_posix()}', OVERRIDE_DATA_PATH TRUE)"
    )
    
    # REMOVED: con.execute("USE silver.main;") 
    # Leaving the default context global allows you to use explicit cross-database syntax:
    # 'silver.main.table' and 'gold.main.table' safely.
    
    return con

con = connect()
print("Building main case metrics dataset...")

try:
    watermark = con.execute(
        "SELECT MAX(date_modified) FROM gold.main.case_metrics"
    ).fetchone()[0]
except:
    watermark = None

# 1. Determine the source extraction strategy based on the gold watermark
if watermark is None:
    print("Gold table empty or missing — full load from silver...")
    source_query = "SELECT * FROM silver.main.dockets"
else:
    print(f"Incremental load from {watermark}...")
    source_query = f"SELECT * FROM silver.main.dockets WHERE date_modified > TIMESTAMP '{watermark}'"

print("Watermark condition settled. Fetching data...")

# 2. FIXED: Instead of .df(), materialize a highly optimized TEMP TABLE directly in DuckDB
# This stops Python from running out of RAM (OOM) during full historical loads.
try:
    con.execute("DROP TABLE IF EXISTS new_silver_temp")
    con.execute(f"CREATE TEMP TABLE new_silver_temp AS {source_query}")
except Exception as sql_err:
    print(f"[CRITICAL SQL ERROR] Failed during data extraction: {sql_err}")
    con.close()
    exit(1)

# Check if we actually grabbed any new records safely
record_count = con.execute("SELECT COUNT(*) FROM new_silver_temp").fetchone()[0]
if record_count == 0:
    print("No new records since last run. Exiting.")
    con.close()
    exit()

print(f"{record_count} new/updated records safely materialized to temp storage...")

# 3. Register your downstream parquet helper file context
cf = courts_file()

# Create target schema if it does not exist yet
# Create target schema structural layout if it does not exist yet
# FIXED: Replaced the broken "SELECT ..." layout with a clean compilation query matching the CTE definition
# Create target schema structural layout if it does not exist yet
# FIXED: Completely explicitly declares column schema types to guarantee 100% stable parsing

con.execute("""
    CREATE TABLE IF NOT EXISTS gold.main.case_metrics (
        id BIGINT,
        court_id VARCHAR,
        case_name VARCHAR,
        date_filed DATE,
        date_terminated DATE,
        date_last_filing DATE,
        nature_of_suit VARCHAR,
        cause VARCHAR,
        blocked BOOLEAN,
        source VARCHAR,
        is_appeal BOOLEAN,
        date_modified TIMESTAMP,
        quarter_filed VARCHAR,
        quarter_terminated VARCHAR,
        docket_number VARCHAR,
        jury_demand BOOLEAN,
        is_active BOOLEAN,
        duration_days INTEGER,
        year_filed INTEGER,
        year_terminated INTEGER,
        year_quarter_filed VARCHAR,
        year_quarter_terminated VARCHAR,
        activity_years BIGINT[],
        activity_quarters VARCHAR[],
        circuit VARCHAR,
        level VARCHAR,
        is_federal BOOLEAN,
        jurisdiction VARCHAR
    )
""")
print("Target analytical metrics schema verified.")

print("Executing analytical merge and deduplication into Gold layer...")

con.execute(f"""
    MERGE INTO gold.main.case_metrics AS tgt
    USING (
        {CASE_METRICS_CTE.format(
            extra_cols=", activity_years, activity_quarters",
            source="new_silver_temp",
            dedup_partition="court_id, docket_number",
        )}
        SELECT
            r.id, r.court_id, r.case_name, r.date_filed, r.date_terminated,
            r.date_last_filing, r.nature_of_suit, r.cause, r.blocked,
            r.source, r.is_appeal, r.date_modified, r.quarter_filed,
            r.quarter_terminated, r.docket_number, r.jury_demand,
            r.is_active, r.duration_days, r.year_filed, r.year_terminated,
            r.year_quarter_filed, r.year_quarter_terminated,
            r.activity_years, r.activity_quarters,
            c.circuit, c.level, c.is_federal, c.jurisdiction
        FROM ranked r
        LEFT JOIN read_parquet('{cf.as_posix()}') c ON r.court_id = c.court_id
        WHERE r.row_num = 1
          AND r.id IS NOT NULL
          AND r.date_filed IS NOT NULL
          AND r.docket_number IS NOT NULL AND r.docket_number != ''
          AND (r.is_active = TRUE OR r.year_terminated > {START_YEAR})
    ) AS src
    ON tgt.id = src.id
    WHEN MATCHED AND src.date_modified > tgt.date_modified THEN UPDATE
    WHEN NOT MATCHED THEN INSERT *
""")

con.execute("DROP TABLE IF EXISTS new_silver_temp")
con.close()
print("Gold upsert complete.")