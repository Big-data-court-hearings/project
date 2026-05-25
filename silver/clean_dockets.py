"""
Silver layer cleaning pipeline for docket data.

This script:
- loads Bronze JSONL data
- cleans and formats the dataset
- selects useful analytical columns
- converts date columns
- removes duplicates
- exports clean parquet data
"""

import pandas as pd

from ingestion.config import (
    DOCKETS_PATH,
    SILVER_PATH
)

# ============================================================
# INPUT / OUTPUT PATHS
# ============================================================

input_file = DOCKETS_PATH / "dockets_raw.jsonl"

output_file = SILVER_PATH / "dockets_clean.parquet"

# ============================================================
# LOAD BRONZE DATA
# ============================================================

print("Loading Bronze JSONL data...")

df = pd.read_json(
    input_file,
    lines=True
)

print(f"Loaded {len(df)} rows")

# ============================================================
# SELECT USEFUL COLUMNS
# ============================================================

selected_columns = [
    "id",
    "court_id",
    "case_name",
    "date_filed",
    "date_terminated",
    "date_last_filing",
    "nature_of_suit",
    "cause",
    "jurisdiction_type",
    "blocked",
    "source"
]

df = df[selected_columns]

# ============================================================
# CONVERT DATE COLUMNS
# ============================================================

date_columns = [
    "date_filed",
    "date_terminated",
    "date_last_filing"
]

for col in date_columns:

    df[col] = pd.to_datetime(
        df[col],
        errors="coerce"
    )

# ============================================================
# REMOVE DUPLICATES
# ============================================================

before = len(df)

df = df.drop_duplicates(subset=["id"])

after = len(df)

print(f"Removed {before - after} duplicate rows")

# ============================================================
# EXPORT SILVER PARQUET
# ============================================================

df.to_parquet(
    output_file,
    index=False
)

print("\nSilver parquet successfully created.")
print(f"Output file : {output_file}")

print("\nDataset overview:")
print(df.info())
print(df.head())