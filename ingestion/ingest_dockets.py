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

from datetime import datetime
from ingestion.api_client import (
    stream_paginated_data
)

from ingestion.config import (
    DOCKETS_PATH,
    MAX_RECORDS
)

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

start_time = time.time()

new_records = 0
duplicate_records = 0

# consecutive duplicate detection
duplicate_streak = 0

# early stopping threshold
MAX_DUPLICATE_STREAK = 100
ENABLE_EARLY_STOPPING = False

with open(
    output_file,
    "a",
    encoding="utf-8"
) as file:

    for row in stream_paginated_data(
        endpoint="dockets/",
        max_records=MAX_RECORDS
    ):

        docket_id = row.get("id")

        # ====================================================
        # SKIP DUPLICATES
        # ====================================================

        if docket_id in existing_ids:

            duplicate_records += 1

            duplicate_streak += 1

            # ====================================================
            # EARLY STOPPING
            # ====================================================

            if (
                ENABLE_EARLY_STOPPING
                and duplicate_streak >= MAX_DUPLICATE_STREAK
            ):

                print(
                    "\nDuplicate threshold reached."
                )

                print(
                    "Stopping incremental ingestion early."
                )

                break

            continue

        # ====================================================
        # APPEND NEW RECORD
        # ====================================================

        file.write(
            json.dumps(row) + "\n"
        )

        existing_ids.add(docket_id)

        new_records += 1

        # reset duplicate streak
        duplicate_streak = 0

        # ====================================================
        # PROGRESS LOGGING
        # ====================================================

        if new_records % 1000 == 0:

            print(
                f"Saved {new_records} new records..."
            )

# ============================================================
# FINAL LOGGING
# ============================================================

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
            "records_per_second"
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
        round(speed, 2)
    ])

print(
    f"Ingestion metadata logged to : "
    f"{log_file}"
)