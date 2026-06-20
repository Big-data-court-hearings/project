"""
Shared utilities for the Gold metrics pipeline.
"""

import sys
import duckdb
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

COURTS_FILE = PROJECT_ROOT / "silver" / "courts" / "courts_classified.parquet"
GOLD_PATH   = PROJECT_ROOT / "gold" / "metrics"

# DuckLake catalog paths
SILVER_CATALOG = (PROJECT_ROOT / "silver_catalog.ducklake").resolve()
SILVER_DATA    = (PROJECT_ROOT / "silver" / "data").resolve()
GOLD_CATALOG   = (PROJECT_ROOT / "gold_catalog.ducklake").resolve()
GOLD_DATA      = (PROJECT_ROOT / "gold" / "data").resolve()

START_YEAR = 2022

QUARTERS_IN_WINDOW = [
    f"{y}-q{q}"
    for y in (2023, 2024, 2025, 2026)
    for q in (1, 2, 3, 4)
    if not (y == 2026 and q > 1)
]


def connect_silver(con: duckdb.DuckDBPyConnection = None) -> duckdb.DuckDBPyConnection:
    """Attaches the silver DuckLake catalog (read-only) to a connection."""
    if con is None:
        con = duckdb.connect()
    con.execute(
        f"ATTACH 'ducklake:{SILVER_CATALOG.as_posix()}' AS silver "
        f"(DATA_PATH '{SILVER_DATA.as_posix()}', OVERRIDE_DATA_PATH TRUE, READ_ONLY TRUE)"
    )
    return con


def connect_gold(con: duckdb.DuckDBPyConnection = None, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Attaches the gold DuckLake catalog to a connection."""
    if con is None:
        con = duckdb.connect()
    GOLD_DATA.mkdir(parents=True, exist_ok=True)
    con.execute(
        f"ATTACH 'ducklake:{GOLD_CATALOG.as_posix()}' AS gold "
        f"(DATA_PATH '{GOLD_DATA.as_posix()}', OVERRIDE_DATA_PATH TRUE"
        + (", READ_ONLY TRUE" if read_only else "") + ")"
    )
    return con


def connect() -> duckdb.DuckDBPyConnection:
    """Returns a plain DuckDB connection (for scripts reading raw Parquet files)."""
    con = duckdb.connect()
    # Force DuckDB to use a conservative memory limit
    con.execute("SET memory_limit = '1GB';") 
    con.execute("SET temp_directory = '/tmp/duckdb_temp';")
    return con


def ensure(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def courts_file() -> Path:
    if COURTS_FILE.exists():
        return COURTS_FILE
    fallback = Path("courts_classified.parquet")
    if fallback.exists():
        return fallback
    raise FileNotFoundError(
        f"Could not locate 'courts_classified.parquet' at {COURTS_FILE} "
        "or in the current working directory."
    )

import os
import time

def remove_stale_locks(catalog_path: Path):
    lock_file = catalog_path.with_suffix(".lock")
    if lock_file.exists():
        # If lock is older than 5 minutes, it's likely stale
        if time.time() - lock_file.stat().st_mtime > 300:
            try:
                os.remove(lock_file)
                print(f"Removed stale lock: {lock_file}")
            except OSError as e:
                print(f"Error removing stale lock: {e}")

def clean_and_connect_silver():
    remove_stale_locks(SILVER_CATALOG)
    return connect_silver()


CASE_METRICS_CTE = """
WITH raw AS (
    SELECT
        id, court_id, case_name, nature_of_suit, cause, blocked, source, is_appeal,
        docket_number, quarter_filed, quarter_terminated, jury_demand,
        TRY_CAST(date_filed        AS DATE)      AS date_filed,
        TRY_CAST(date_terminated   AS DATE)      AS date_terminated,
        TRY_CAST(date_last_filing  AS DATE)      AS date_last_filing,
        TRY_CAST(date_modified     AS TIMESTAMP) AS date_modified
        {extra_cols}
    FROM {source}
),
ranked AS (
    SELECT
        *,
        CASE WHEN date_terminated IS NULL THEN TRUE ELSE FALSE END AS is_active,
        CASE
            WHEN date_filed IS NOT NULL AND date_terminated IS NOT NULL
            THEN date_diff('day', date_filed, date_terminated)
        END AS duration_days,
        CASE WHEN date_filed       IS NOT NULL THEN year(date_filed)       END AS year_filed,
        CASE WHEN date_terminated  IS NOT NULL THEN year(date_terminated)  END AS year_terminated,
        CASE
            WHEN quarter_terminated IS NOT NULL AND quarter_terminated != 'q0'
            THEN CAST(year(date_terminated) AS VARCHAR) || '-' || quarter_terminated
        END AS year_quarter_terminated,
        CASE
            WHEN quarter_filed IS NOT NULL AND quarter_filed != 'q0'
            THEN CAST(year(date_filed) AS VARCHAR) || '-' || quarter_filed
        END AS year_quarter_filed,
        ROW_NUMBER() OVER (
            PARTITION BY {dedup_partition}
            ORDER BY date_modified DESC, id DESC
        ) AS row_num
    FROM raw
)
"""