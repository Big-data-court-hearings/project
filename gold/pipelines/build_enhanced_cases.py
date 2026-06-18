"""
Builds and incrementally maintains the gold case_metrics table in a DuckLake catalog.
On each run, only silver records newer than the gold watermark (MAX date_modified)
are processed and upserted — new cases are inserted, updated cases are merged.
Full reprocessing only happens on the first run when the gold table does not exist yet.
"""

import duckdb
import numpy as np
import pandas as pd
import xgboost as xgb
from pathlib import Path
from _common import (
    GOLD_PATH, CASE_METRICS_CTE,
    connect, ensure, courts_file, START_YEAR,
)

# ── load trained XGBoost instance ──
_SCRIPT_DIR      = Path(__file__).resolve().parent
PROJECT_ROOT     = _SCRIPT_DIR.parent.parent
MODEL_DIR        = PROJECT_ROOT / "model_training" / "models"
_MODEL_FILE      = MODEL_DIR / "binary_model.ubj"
_COURT_STATS_FILE = MODEL_DIR / "court_stats.parquet"

LONG_CASE_THRESHOLD = 0.34   # threshold for maximum recall

INFERENCE_FEATURES = [
    "court_id", "blocked", "is_appeal", "jury_demand",
    "quarter_filed", "circuit", "level", "is_federal", "jurisdiction",
    "court_censoring_rate", "court_case_volume",
]


output_file= ensure(GOLD_PATH / "case_enhanced.parquet")
base_path    = Path(__file__).parent
SILVER_CATALOG = (base_path / ".." / "silver_catalog.ducklake").resolve()
SILVER_DATA    = (base_path / ".." / "silver" / "data").resolve()
GOLD_CATALOG   = (base_path / ".." / "gold_catalog.ducklake").resolve()
GOLD_DATA      = (base_path / ".." / "gold" / "data").resolve()

def connect():
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent.parent
    
    # Paths for both catalogs
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
    
    # ATTACH GOLD DATABASE 
    con.execute(
        f"ATTACH 'ducklake:{GOLD_CAT_PATH.as_posix()}' AS gold "
        f"(DATA_PATH '{GOLD_DAT_PATH.as_posix()}', OVERRIDE_DATA_PATH TRUE)"
    )
    
    
    return con

con = connect()
print("Building main case metrics dataset...")

try:
    watermark = con.execute(
        "SELECT MAX(date_modified) FROM gold.main.case_metrics"
    ).fetchone()[0]
except:
    watermark = None

# Determine the source extraction strategy based on the gold watermark
if watermark is None:
    print("Gold table empty or missing — full load from silver...")
    source_query = "SELECT * FROM silver.main.dockets"
else:
    print(f"Incremental load from {watermark}...")
    source_query = f"SELECT * FROM silver.main.dockets WHERE date_modified > TIMESTAMP '{watermark}'"

print("Watermark condition settled. Fetching data...")

# FIXED: Instead of .df(), materialize a highly optimized TEMP TABLE directly in DuckDB
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

# Run XGBoost inference on active cases and register predictions as a temp table
# ── Only cases where is_active = TRUE receive a prediction; the rest get NULL.

con.execute("DROP TABLE IF EXISTS predictions_temp")

active_ids: list[int] = []
if _MODEL_FILE.exists() and _COURT_STATS_FILE.exists():
    print("Loading XGBoost binary classifier...")
    bst = xgb.Booster()
    bst.load_model(str(_MODEL_FILE))

    # Pull active records with the columns the model expects
    df_active: pd.DataFrame = con.execute(f"""
        SELECT
            s.id,
            s.court_id,
            s.blocked,
            s.is_appeal,
            s.jury_demand,
            s.quarter_filed,
            cs.court_censoring_rate,
            cs.court_case_volume,
            DATEDIFF('day', s.date_filed::DATE, CURRENT_DATE::DATE) AS days_open
        FROM new_silver_temp s
        LEFT JOIN read_parquet('{_COURT_STATS_FILE.as_posix()}') cs
            ON s.court_id = cs.court_id
        WHERE s.date_terminated IS NULL
    """).df()

    if df_active.empty:
        print("No active cases in this batch — skipping inference.")
        con.execute("CREATE TEMP TABLE predictions_temp (id BIGINT, solved_within_year_since_filing BOOLEAN)")
    else:
        # Join court classification columns (circuit, level, is_federal, jurisdiction)
        cf_tmp = courts_file()
        df_courts: pd.DataFrame = con.execute(
            f"SELECT court_id, circuit, level, is_federal, jurisdiction "
            f"FROM read_parquet('{cf_tmp.as_posix()}')"
        ).df()
        df_active = df_active.merge(df_courts, on="court_id", how="left")
        # only consider cases that have been open for less than a year
        df_over_year = df_active[df_active["days_open"] >= 365][["id"]].copy()
        df_over_year["solved_within_year_since_filing"] = False
        df_under_year = df_active[df_active["days_open"] < 365].copy()

        # Encode categoricals and align to expected feature order
        df_feat = df_under_year[INFERENCE_FEATURES].copy()
        for col in df_feat.select_dtypes(include=["object"]).columns:
            df_feat[col] = df_feat[col].astype("category")
        df_feat["is_federal"] = df_feat["is_federal"].fillna(False).astype(bool)

        dmat = xgb.DMatrix(df_feat, enable_categorical=True)
        proba = bst.predict(dmat)

        # solved_within_year = NOT long  →  True when predicted_long == 0
        solved = (proba < LONG_CASE_THRESHOLD)
        
        df_preds = pd.DataFrame({
            "id": df_under_year["id"].values,
            "solved_within_year_since_filing": solved,
        })
        df_preds = pd.concat([
            df_preds,          # XGBoost output for < 1 year cases
            df_over_year,      # hardcoded False for >= 1 year cases
        ], ignore_index=True)
        
        active_ids = df_preds["id"].tolist()

        con.register("_df_preds", df_preds)
        con.execute("""
            CREATE TEMP TABLE predictions_temp AS
            SELECT
                CAST(id AS BIGINT)                    AS id,
                solved_within_year_since_filing::BOOLEAN AS solved_within_year_since_filing
            FROM _df_preds
        """)
        con.unregister("_df_preds")
        print(f"Inference complete — {len(df_preds)} active cases scored "
              f"({solved.sum()} predicted to resolve within a year).")
else:
    print(f"[WARN] Model artefacts not found under {MODEL_DIR}. "
          "solved_within_year_since_filing will be NULL for all rows.")
    con.execute("CREATE TEMP TABLE predictions_temp (id BIGINT, solved_within_year_since_filing BOOLEAN)")

cf = courts_file()

# target schema
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
        jurisdiction VARCHAR,
        solved_within_year_since_filing BOOLEAN
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
            c.circuit, c.level, c.is_federal, c.jurisdiction,
            -- NULL for closed cases (is_active = FALSE); prediction for open ones
            p.solved_within_year_since_filing
        FROM ranked r
        LEFT JOIN read_parquet('{cf.as_posix()}') c ON r.court_id = c.court_id
        LEFT JOIN predictions_temp              p ON r.id        = p.id
        WHERE r.row_num = 1
          AND r.id IS NOT NULL
          AND r.date_filed IS NOT NULL
          AND r.docket_number IS NOT NULL AND r.docket_number != ''
          AND (r.is_active = TRUE OR r.year_terminated > {START_YEAR})
    ) AS src
    ON tgt.id = src.id
    WHEN MATCHED AND src.date_modified > tgt.date_modified THEN UPDATE SET
        solved_within_year_since_filing = src.solved_within_year_since_filing
    WHEN NOT MATCHED THEN INSERT *
""")

con.execute("DROP TABLE IF EXISTS new_silver_temp")
con.execute("DROP TABLE IF EXISTS predictions_temp")
con.close()
print("Gold upsert complete.")