"""
This script accesses with Kafka the bronze data, then cleans them,
processes them, and stores them in a DuckLake table: an open lakehouse
format made of Parquet data files plus a transactional DuckDB metadata
catalog (snapshots, schema, ACID commits).
It automatically shuts down if the users presses Ctrl + C.
"""

from quixstreams import Application
import os
import json
import time  
import pandas as pd
import numpy as np
import pyarrow as pa
import duckdb
from datetime import datetime
from pathlib import Path


broker = os.getenv("KAFKA_BROKER", "localhost:9092")
base_path = Path(__file__).parent



# --- DuckLake storage configuration ---
# CATALOG_PATH is the DuckDB file holding all DuckLake metadata (schema,
# snapshots, transaction log). DATA_PATH is where the underlying Parquet
# files actually live. Both replace the old "silver/*.parquet" file dump.
CATALOG_PATH = (base_path / ".." / "silver_catalog.ducklake").resolve()
DATA_PATH = (base_path / ".." / "silver" / "data").resolve()
EXISTING_PARQUET = Path(base_path / ".." / "silver" / "data")


LAKE_NAME = "silver"
TABLE_NAME = "dockets"


def calculate_activity_ranges(row):
    """
    Calculates the lists of active years and quarters for each row.
    Formats quarters exactly as 'YYYY-qX' (e.g., '2026-q1').
    If date_terminated is null, it extends the calculation to the current quarter (June 2026).
    """
    if pd.isnull(row["date_filed"]):
        return [], []

    start_date = row["date_filed"]
    # If the case is active, we use the current timestamp (June 2026)
    end_date = row["date_terminated"] if pd.notnull(row["date_terminated"]) else pd.Timestamp(datetime.now())

    if start_date > end_date:
        return [], []

    # 1. Calculation of active years
    years = [str(y) for y in range(start_date.year, end_date.year + 1)]

    # 2. Calculation of active quarters with native Pandas 'YYYY-qX' formatting
    quarter_range = pd.date_range(
        start=start_date.to_period('Q').start_time,
        end=end_date.to_period('Q').start_time,
        freq='QS'
    )
    # dt.to_period('Q') returns something like '2026Q1'. We convert it to '2026-q1'
    quarters = [str(dt.to_period('Q')).lower().replace('q', '-q') for dt in quarter_range]

    return years, quarters


def get_ducklake_connection():
    """
    Opens a DuckDB connection and attaches the silver DuckLake catalog,
    creating the catalog file and data folder on first run.
    """
    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    con.execute(
        f"ATTACH 'ducklake:{CATALOG_PATH.as_posix()}' AS {LAKE_NAME} "
        f"(DATA_PATH '{DATA_PATH.as_posix()}', OVERRIDE_DATA_PATH TRUE)"

    )
    con.execute(f"USE {LAKE_NAME}")
    return con


def upsert_batch(con, df_clean):
    """
    Registers the cleaned batch as an Arrow table and upserts it into the
    DuckLake table, keyed on docket id.
    """
    arrow_batch = pa.Table.from_pandas(df_clean, preserve_index=False)
    con.register("batch_df", arrow_batch)

    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} AS 
        SELECT * REPLACE (
            CAST(docket_number AS VARCHAR) AS docket_number
        )
        FROM batch_df LIMIT 0
    """)

    target_cols = [
        "id", "court_id", "case_name", "date_filed", "date_terminated",
        "date_last_filing", "nature_of_suit", "cause", "jurisdiction_type",
        "blocked", "source", "docket_number", "date_modified", "is_appeal",
        "jury_demand", "quarter_terminated", "quarter_filed",
        "activity_years", "activity_quarters"
    ]
    insert_cols = ", ".join(target_cols)
    insert_vals = ", ".join(f"src.{c}" for c in target_cols)

    # Explicitly maps and safely casts every single column incoming from PyArrow
    con.execute(f"""
        MERGE INTO {TABLE_NAME} AS tgt
        USING (
            SELECT 
                CAST(id AS BIGINT) AS id,
                court_id,
                case_name,
                date_filed,
                date_terminated,
                date_last_filing,
                nature_of_suit,
                cause,
                jurisdiction_type,
                blocked,
                source,
                CAST(docket_number AS VARCHAR) AS docket_number,
                TRY_CAST(date_modified AS TIMESTAMP) AS date_modified,
                is_appeal,
                jury_demand,
                quarter_terminated,
                quarter_filed,
                TRY_CAST(activity_years AS BIGINT[]) AS activity_years,
                activity_quarters
            FROM batch_df
        ) AS src
        ON tgt.id = src.id
        WHEN MATCHED AND src.date_modified > tgt.date_modified THEN UPDATE
        WHEN NOT MATCHED THEN INSERT ({insert_cols}) VALUES ({insert_vals})
    """)

    con.unregister("batch_df")


def main():
    app = Application(
        broker_address=broker,
        consumer_group="silver_cleaner",
        auto_offset_reset="earliest"
    )

    con = get_ducklake_connection()

    with app.get_consumer() as consumer:
        consumer.subscribe(["bronze"])
        print("Fetching bronze data ...")

        last_message_time = time.time()

        while True:
            msg = consumer.poll(1)

            if msg is None:
                idle_duration = time.time() - last_message_time
                spinner = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
                frame = spinner[int(idle_duration * 8) % len(spinner)]
                print(f"\r{frame} Waiting... ({int(idle_duration)}s)", end="", flush=True)
                continue

            elif msg.error() is not None:
                raise Exception(msg.error())

            # Reset the idle timer as soon as a valid message is picked up
            last_message_time = time.time()
            print()
            try:
                page_results = json.loads(msg.value().decode("utf8"))
                if not page_results:
                    consumer.store_offsets(msg)
                    consumer.commit(msg)
                    continue

                print(f"Loading {len(page_results)} records...")
                offset = msg.offset()

                df = pd.DataFrame(page_results)
                df_clean = df.reindex(columns=[
                    "id", "court_id", "case_name", "date_filed",
                    "date_terminated", "date_last_filing", "nature_of_suit",
                    "cause", "jurisdiction_type", "blocked", "source", "date_modified", "docket_number", "jury_demand"
                ])

                # 1. Parse into real datetime objects for calendar math
                df_clean["date_filed"] = pd.to_datetime(df_clean["date_filed"], format="%Y-%m-%d", errors="coerce")
                df_clean["date_terminated"] = pd.to_datetime(df_clean["date_terminated"], format="%Y-%m-%d", errors="coerce")
                df_clean["date_last_filing"] = pd.to_datetime(df_clean["date_last_filing"], format="%Y-%m-%d", errors="coerce")
                df_clean["date_modified"] = pd.to_datetime(df_clean["date_modified"], errors="coerce")

                # 2. Extract single quarter codes dynamically
                df_clean["quarter_filed"] = df_clean["date_filed"].apply(
                    lambda x: f"q{int((x.month - 1) / 3) + 1}" if pd.notnull(x) else "q0"
                )

                df_clean["quarter_terminated"] = df_clean["date_terminated"].apply(
                    lambda x: f"q{int((x.month - 1) / 3) + 1}" if pd.notnull(x) else "q0"
                )

                activity_res = df_clean.apply(calculate_activity_ranges, axis=1)
                df_clean["activity_years"] = [res[0] for res in activity_res]
                df_clean["activity_quarters"] = [res[1] for res in activity_res]

                # 3. CONVERT TO STRICT STANDARD ISO STRINGS (%Y-%m-%d)
                date_cols = ["date_filed", "date_terminated", "date_last_filing"]
                for col in date_cols:
                    df_clean[col] = df_clean[col].apply(
                        lambda x: x.strftime("%Y-%m-%d") if pd.notnull(x) else None
                    )

                df_clean["is_appeal"] = False
                if "original_court_info" in df.columns:
                    invalid_vals = ["None", "none", "", None]
                    df_clean["is_appeal"] = ~df["original_court_info"].isin(invalid_vals)
                df_clean["jury_demand"] = df_clean["jury_demand"].isin(["Plaintiff", "Defendant", "Both"])

                # Clean out structural index records lacking critical data identifiers
                df_clean = df_clean.dropna(subset=["id", "date_filed", "date_modified"], how="any")
                df_clean = df_clean[df_clean["date_filed"] != ""]

                if df_clean.empty:
                    print("Batch empty after filter operations. Skipping save.")
                    consumer.store_offsets(msg)
                    consumer.commit(msg)
                    continue

                # Pin "id" to a stable integer type so the join key stays
                # consistent across batches (avoids float-vs-int drift from
                # earlier NaNs, which would break the MERGE INTO match)
                df_clean["id"] = df_clean["id"].astype("int64")

                upsert_batch(con, df_clean)
                print(f"Upserted {len(df_clean)} records into {LAKE_NAME}.{TABLE_NAME} (offset {offset})")
            except Exception as e:
                print(f"[ERROR] Failed to process offset {msg.offset()}: {e}")
                quarantine_path = base_path / ".." / "bronze" / "quarantine" / f"offset_{msg.offset()}.json"
                quarantine_path.parent.mkdir(parents=True, exist_ok=True)
                quarantine_path.write_bytes(msg.value())
            consumer.store_offsets(msg)
            consumer.commit(msg)

    con.close()
    print("Consumer engine stopped safely.")


if __name__ == "__main__":
    main()