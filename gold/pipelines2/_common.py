"""
Shared utilities for the Gold metrics pipeline.
"""

import sys
import duckdb
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

from ingestion.config import SILVER_PATH

SILVER_GLOB = (Path(SILVER_PATH) / "*.parquet").as_posix()
COURTS_FILE = PROJECT_ROOT / "silver" / "courts" / "courts_classified.parquet"
GOLD_PATH = PROJECT_ROOT / "gold" / "metrics"
START_YEAR = 2022  # Exclusive lower bound for the Observatory window

QUARTERS_IN_WINDOW = [
    f"{y}-q{q}"
    for y in (2023, 2024, 2025, 2026)
    for q in (1, 2, 3, 4)
    if not (y == 2026 and q > 1)
]


def connect() -> duckdb.DuckDBPyConnection:
    return duckdb.connect()


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


# Reusable SQL fragment for the enriched case CTE (used by build_case_metrics and build_database_metrics)
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
