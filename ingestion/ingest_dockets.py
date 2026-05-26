"""
Incremental docket ingestion script.

Downloads docket data from CourtListener API
and appends only unseen records
to the Bronze JSONL layer.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

sys.path.append(str(PROJECT_ROOT))

import json
import time
import csv
import argparse
import shelve

from datetime import datetime, date
from ingestion.api_client import (
    stream_paginated_data
)

from ingestion.checkpoint import (
    load_checkpoint,
    save_checkpoint
)

from ingestion.config import (
    DOCKETS_PATH,
    MAX_RECORDS
)

    ID_INDEX_PATH = PROJECT_ROOT / "logs" / "id_index.db"


    def parse_args():
        parser = argparse.ArgumentParser(description="Ingest dockets (optionally historical windows)")
        parser.add_argument("--start-date", help="Start date (YYYY-MM-DD) for historical ingestion")
        parser.add_argument("--end-date", help="End date (YYYY-MM-DD) for historical ingestion")
        parser.add_argument("--window", choices=("year", "month"), default="year", help="Window size for historical ingestion")
        parser.add_argument("--use-disk-index", action="store_true", help="Use disk-backed ID index to avoid loading all IDs into memory")
        parser.add_argument("--disable-early-stopping", action="store_true", help="Disable improved early stopping for full scans")
        return parser.parse_args()


    def year_windows(start: date, end: date):
        cur = date(start.year, 1, 1)
        while cur.year <= end.year:
            wstart = max(cur, start)
            wend = min(date(cur.year, 12, 31), end)
            yield wstart, wend
            cur = date(cur.year + 1, 1, 1)


    def month_windows(start: date, end: date):
        cur = date(start.year, start.month, 1)
        while cur <= end:
            # compute last day of month
            if cur.month == 12:
                next_month = date(cur.year + 1, 1, 1)
            else:
                next_month = date(cur.year, cur.month + 1, 1)

            wstart = max(cur, start)
            wend = min(next_month - timedelta(days=1), end)
            yield wstart, wend
            cur = next_month

# ============================================================
# OUTPUT FILE
# ============================================================

output_file = (
    DOCKETS_PATH / "dockets_raw.jsonl"
)

log_file = (
    PROJECT_ROOT
    / "logs"
    / "ingestion_history.csv"
)

# ============================================================
# LOAD EXISTING IDS
# ============================================================

existing_ids = set()

if output_file.exists():

    print("Loading existing Bronze IDs...")

    with open(
        output_file,
        "r",
        encoding="utf-8"
    ) as file:

        for line in file:

            try:

                row = json.loads(line)

                existing_ids.add(row["id"])

            except Exception:

                continue

print(
    f"Loaded {len(existing_ids)} existing IDs"
)

# ============================================================
# INCREMENTAL INGESTION
# ============================================================

# runtime
start_time = time.time()

new_records = 0
duplicate_records = 0
total_processed = 0

# consecutive duplicate detection
duplicate_streak = 0

# early stopping threshold
MAX_DUPLICATE_STREAK = 100
ENABLE_EARLY_STOPPING = True

# checkpoint save policy
CHECKPOINT_SAVE_INTERVAL = 1000  # save after this many new records
CHECKPOINT_SAVE_SECONDS = 60     # or this many seconds

# Load checkpoint and pass date filter to API
checkpoint_date = load_checkpoint("dockets")

params = None

if checkpoint_date:
    params = {"date_filed__gte": checkpoint_date}


with open(
    output_file,
    "a",
    encoding="utf-8"
) as file:

    # track the latest date_filed and id seen during this run
    latest_date_seen = None
    latest_id_for_latest_date = None

    # stats
    stats = {"pages_fetched": 0}

    last_checkpoint_save = time.time()

    try:
        for row in stream_paginated_data(
            endpoint="dockets/",
            max_records=MAX_RECORDS,
            params=params,
            stats=stats
        ):

            docket_id = row.get("id")

            total_processed += 1

        # ====================================================
        # SKIP DUPLICATES
        # ====================================================

            if docket_id in existing_ids:

                duplicate_records += 1

                duplicate_streak += 1

                # improved early stopping: if we hit a long duplicate streak
                # and we've already fetched several pages, assume we're
                # caught up and stop to avoid scanning the rest of the API
                if (
                    ENABLE_EARLY_STOPPING
                    and duplicate_streak >= MAX_DUPLICATE_STREAK
                    and stats.get("pages_fetched", 0) > 5
                ):

                    print("\nDuplicate threshold reached; stopping early.")
                    break

                continue

            # ====================================================
            # TRACK LATEST DATE FILED + ID
            # ====================================================

            row_date = row.get("date_filed")

            if row_date:
                if (
                    latest_date_seen is None
                    or row_date > latest_date_seen
                    or (row_date == latest_date_seen and docket_id > (latest_id_for_latest_date or ""))
                ):
                    latest_date_seen = row_date
                    latest_id_for_latest_date = docket_id

        # ====================================================
        # APPEND NEW RECORD
        # ====================================================

            # ====================================================
            # APPEND NEW RECORD
            # ====================================================

            file.write(json.dumps(row) + "\n")

            existing_ids.add(docket_id)

            new_records += 1

            # reset duplicate streak
            duplicate_streak = 0

            # periodic checkpoint save by count or time
            now = time.time()

            if (
                new_records % CHECKPOINT_SAVE_INTERVAL == 0
                or now - last_checkpoint_save >= CHECKPOINT_SAVE_SECONDS
            ) and latest_date_seen:
                try:
                    save_checkpoint("dockets", latest_date_seen, latest_id_for_latest_date)
                    last_checkpoint_save = now
                    print(f"Periodic checkpoint saved: {latest_date_seen} / {latest_id_for_latest_date}")
                except Exception:
                    print("Warning: failed to save periodic checkpoint.")

        # ====================================================
        # PROGRESS LOGGING
        # ====================================================

            if new_records % 1000 == 0:

                print(f"Saved {new_records} new records...")

    except KeyboardInterrupt:
        print("\nInterrupted by user; saving checkpoint before exit...")

    finally:
        # ensure checkpoint is saved on both normal and interrupted exits
        if latest_date_seen:
            try:
                save_checkpoint("dockets", latest_date_seen, latest_id_for_latest_date)
                print(f"Saved final checkpoint: {latest_date_seen} / {latest_id_for_latest_date}")
            except Exception:
                print("Warning: failed to save final checkpoint.")

# ============================================================
# FINAL LOGGING
# ============================================================

# ============================================================
# UPDATE CHECKPOINT
# ============================================================

if latest_date_seen:
    try:
        save_checkpoint("dockets", latest_date_seen, latest_id_for_latest_date)
        print(f"Updated checkpoint to: {latest_date_seen} / {latest_id_for_latest_date}")
    except Exception:
        print("Warning: failed to save checkpoint.")


print("\nIncremental ingestion completed.")

print(f"New records added : {new_records}")

print(f"Duplicates skipped : {duplicate_records}")

print(f"Total Bronze records : {len(existing_ids)}")

# ============================================================
# RUNTIME METRICS
# ============================================================

elapsed = time.time() - start_time

speed = 0

if elapsed > 0:

    speed = (
        new_records / elapsed
    )

print(f"Runtime : {elapsed:.2f} seconds")

print(
    f"Ingestion speed : "
    f"{speed:.2f} records/sec"
)

# ============================================================
# INGESTION STATISTICS
# ============================================================

pages_fetched = stats.get("pages_fetched", 0)
duplicate_ratio = 0
if total_processed > 0:
    duplicate_ratio = duplicate_records / total_processed

print(f"API pages fetched : {pages_fetched}")
print(f"Total records processed : {total_processed}")
print(f"Duplicate ratio : {duplicate_ratio:.3f}")


# ============================================================
# INGESTION HISTORY LOGGING
# ============================================================

file_exists = log_file.exists()

with open(
    log_file,
    "a",
    newline="",
    encoding="utf-8"
) as csvfile:

    writer = csv.writer(csvfile)

    # ========================================================
    # HEADER
    # ========================================================

    if not file_exists:

        writer.writerow([
            "timestamp",
            "new_records",
            "duplicates_skipped",
            "total_bronze_records",
            "runtime_seconds",
            "records_per_second",
            "pages_fetched",
            "duplicate_ratio"
        ])

    # ========================================================
    # METADATA ROW
    # ========================================================

    writer.writerow([
        datetime.now().isoformat(),
        new_records,
        duplicate_records,
        len(existing_ids),
        round(elapsed, 2),
        round(speed, 2),
        pages_fetched,
        round(duplicate_ratio, 4)
    ])

print(
    f"Ingestion metadata logged to : "
    f"{log_file}"
)