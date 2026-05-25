"""
Gold analytical case metrics table.

This script creates an enriched analytical dataset
from the Silver docket dataset.
"""

import duckdb

from ingestion.config import (
    SILVER_PATH,
    GOLD_PATH
)

# ============================================================
# PATHS
# ============================================================

silver_file = SILVER_PATH / "dockets_clean.parquet"

output_file = GOLD_PATH / "case_metrics.parquet"

# ============================================================
# DUCKDB CONNECTION
# ============================================================

print("Connecting to DuckDB...")

con = duckdb.connect()

# ============================================================
# BUILD ANALYTICAL TABLE
# ============================================================

print("Building case metrics dataset...")

query = f"""
SELECT

    id,
    court_id,
    case_name,

    date_filed,
    date_terminated,
    date_last_filing,

    nature_of_suit,
    jurisdiction_type,
    cause,

    blocked,
    source,

    CASE
        WHEN date_terminated IS NULL
        THEN TRUE
        ELSE FALSE
    END AS is_active,

    CASE
        WHEN
            date_filed IS NOT NULL
            AND date_terminated IS NOT NULL
        THEN date_diff(
            'day',
            date_filed,
            date_terminated
        )
        ELSE NULL
    END AS duration_days,

    CASE
        WHEN date_filed IS NOT NULL
        THEN year(date_filed)
        ELSE NULL
    END AS year_filed,

    CASE
        WHEN date_terminated IS NOT NULL
        THEN year(date_terminated)
        ELSE NULL
    END AS year_terminated

FROM read_parquet('{silver_file}')
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