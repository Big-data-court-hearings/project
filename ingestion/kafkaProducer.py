"""
Incremental page-by-page docket ingestion script with Kafka streaming.

Downloads docket data from CourtListener API, filters out duplicate IDs 
using local history maps, and produces raw data blocks page-by-page 
directly to the Kafka Bronze layer.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

import json
import time
import csv
import argparse
import os
from datetime import datetime, timedelta

from quixstreams import Application

from ingestion.api_client import stream_paginated_data
from ingestion.checkpoint import load_checkpoint, save_checkpoint
from ingestion.config import DOCKETS_PATH, MAX_RECORDS



# Tracking paths
log_file = PROJECT_ROOT / "logs" / "ingestion_history.csv"
output_file = DOCKETS_PATH / "dockets_raw.jsonl"


def parse_args():
    parser = argparse.ArgumentParser(description="Ingest dockets to Kafka page-by-page")
    parser.add_argument("--start-date", help="Start date (YYYY-MM-DD) for historical ingestion")
    parser.add_argument("--disable-early-stopping", action="store_true", help="Disable early stopping for full scans")
    return parser.parse_args()


def obtain_date():
    """Determines start date from checkpoint, manual overrides, or fallback defaults."""
    checkpoint_data = load_checkpoint("dockets")
    default_fallback = (datetime.today() - timedelta(hours=4)).strftime('%Y-%m-%dT%H:%M:%S')
    
    # Safely extract initial date string even if checkpoint is a dictionary payload structure
    if checkpoint_data:
        if isinstance(checkpoint_data, dict):
            initial_date = checkpoint_data.get("date")
        else:
            initial_date = checkpoint_data
        print(f"Found existing checkpoint date: {initial_date}")
    else:
        print(f"No checkpoint found. Defaulting to 4 hours ago: {default_fallback}")
        initial_date = default_fallback

    # Fallback to bypass interactive inputs if running completely automated/non-TTY inside Docker
    if not sys.stdin.isatty():
        print(f"Non-interactive environment. Automatically proceeding with focus date: {initial_date}")
        return initial_date

    answered = False
    while not answered:
        response = input(f"\nCurrent date focus is set to [{initial_date}]. Do you want to use a different date? (y/n): ")
        if response.lower() == "y":
            raw_input = input("Please write a different date in the '%Y-%m-%dT%H:%M:%S' format: ")
            try:
                datetime.strptime(raw_input, '%Y-%m-%dT%H:%M:%S')
                initial_date = raw_input
                answered = True
            except ValueError:
                print("Invalid format mismatch. Please use 'YYYY-MM-DDTHH:MM:SS'.")
        elif response.lower() == "n":
            answered = True
        else:
            print("Please type 'y' or 'n'.")
            
    return initial_date


def load_existing_ids():
    """Builds an in-memory tracking set of already ingested items."""
    existing_ids = set()
    if output_file.exists():
        print("Building initial duplicate protection map from historic Bronze log...")
        with open(output_file, "r", encoding="utf-8") as file:
            for line in file:
                try:
                    row = json.loads(line)
                    existing_ids.add(str(row["id"]))
                except Exception:
                    continue
    print(f"Loaded {len(existing_ids)} existing IDs into memory matrix.")
    return existing_ids


def main():
    args = parse_args()
    
    # Setup QuixStreams Application Infrastructure
    broker = os.getenv("KAFKA_BROKER", "localhost:9092")
    app = Application(
        broker_address=broker,
        loglevel="INFO",
        producer_extra_config={
            "compression.type": "gzip",
            "max.in.flight.requests.per.connection": 1
        }
    )

    existing_ids = load_existing_ids()
    start_time = time.time()

    new_records = 0
    duplicate_records = 0
    total_processed = 0
    duplicate_streak = 0

    MAX_DUPLICATE_STREAK = 100
    ENABLE_EARLY_STOPPING = not args.disable_early_stopping
    CHECKPOINT_SAVE_INTERVAL = 1000 
    CHECKPOINT_SAVE_SECONDS = 60     

    if args.start_date:
        last_update = args.start_date
    else:
        last_update = obtain_date()

    # ─── FIXED CHECKPOINT UNPACKING ENGINE ──────────────────────────────────────
    params = None
    if last_update:
        # If last_update is still the dictionary read directly from checkpoints, extract the raw date string
        if isinstance(last_update, dict):
            actual_date_str = last_update.get("date")
        else:
            actual_date_str = last_update
            
        if actual_date_str:
            params = {"date_modified__gt": actual_date_str}
    
    latest_date_seen = None
    latest_id_for_latest_date = None
    stats = {"pages_fetched": 0}
    last_checkpoint_save = time.time()

    print("Initializing connection to Kafka topic: [bronze]...")

    with app.get_producer() as producer:
        try:
            page_buffer = []
            last_page_count = 0

            for row in stream_paginated_data(
                endpoint="dockets/",
                max_records=MAX_RECORDS,
                params=params,
                stats=stats
            ):
                current_page_count = stats.get("pages_fetched", 1)
                
                # ─── PAGE BOUNDARY DETECTOR ──────────────────────────────────────
                # If the API client flipped to a new page, ship the buffered page out 
                if current_page_count != last_page_count and page_buffer:
                    producer.produce(
                        topic="bronze",
                        key=f"page_{last_page_count}",
                        value=json.dumps(page_buffer)
                    )
                    print(f"✉️ Shipped page batch {last_page_count} with {len(page_buffer)} records to Kafka.")
                    new_records += len(page_buffer)
                    page_buffer = []  # Clear memory for the next page array
                
                last_page_count = current_page_count
                docket_id = str(row.get("id"))
                total_processed += 1

                # Duplicate protection check
                if docket_id in existing_ids:
                    duplicate_records += 1
                    duplicate_streak += 1

                    if (
                        ENABLE_EARLY_STOPPING
                        and duplicate_streak >= MAX_DUPLICATE_STREAK
                        and current_page_count > 5
                    ):
                        print(f"Duplicate threshold ({MAX_DUPLICATE_STREAK}) reached. Halting pipeline execution.")
                        break
                    continue

                # Checkpoint data tracking
                row_date = row.get("date_modified")
                if row_date:
                    if (
                        latest_date_seen is None
                        or row_date > latest_date_seen
                        or (row_date == latest_date_seen and docket_id > (latest_id_for_latest_date or ""))
                    ):
                        latest_date_seen = row_date
                        latest_id_for_latest_date = docket_id

                # Accumulate row item into current active page list
                page_buffer.append(row)

                # Keep local record file updated as historical reference index
                with open(output_file, "a", encoding="utf-8") as fallback_file:
                    fallback_file.write(json.dumps(row) + "\n")

                existing_ids.add(docket_id)
                duplicate_streak = 0

                # Periodic configuration state checkpointing
                now = time.time()
                if (
                    new_records % CHECKPOINT_SAVE_INTERVAL == 0
                    or now - last_checkpoint_save >= CHECKPOINT_SAVE_SECONDS
                ) and latest_date_seen:
                    try:
                        save_checkpoint("dockets", latest_date_seen, latest_id_for_latest_date)
                        last_checkpoint_save = now
                        #print(f"System checkpoint log saved at date: {latest_date_seen}")
                    except Exception as e:
                        print(f"Failed saving automatic checkpoint state: {e}")

            # ─── FINAL CLEANUP SHIPMENT ──────────────────────────────────────
            # Don't leave any leftover records sitting in the last page buffer
            if page_buffer:
                producer.produce(
                    topic="bronze",
                    key=f"page_{last_page_count}",
                    value=json.dumps(page_buffer)
                )
                print(f"✉️ Shipped final page batch {last_page_count} with {len(page_buffer)} records to Kafka.")
                new_records += len(page_buffer)

        except KeyboardInterrupt:
            print("\nExecution halted by operator command. Saving checkpoints...")
        finally:
            if latest_date_seen:
                try:
                    save_checkpoint("dockets", latest_date_seen, latest_id_for_latest_date)
                    print(f"Final transaction state checkpoint logged at: {latest_date_seen}")
                except Exception as e:
                    print(f"Failed logging checkpoint during teardown: {e}")
            
            # Flush pipeline out to cluster brokers safely
            producer.flush()

    # ============================================================
    # PIPELINE METRICS SUMMARY
    # ============================================================
    elapsed = time.time() - start_time
    speed = new_records / elapsed if elapsed > 0 else 0
    pages_fetched = stats.get("pages_fetched", 0)
    duplicate_ratio = duplicate_records / total_processed if total_processed > 0 else 0

    print("\n" + "="*50)
    print("📈 INGESTION PIPELINE EXECUTION METRICS")
    print("="*50)
    print(f"Total Records Streamed to Kafka : {new_records}")
    print(f"Duplicates Filtered Out         : {duplicate_records}")
    print(f"Overall Total Records Identified: {len(existing_ids)}")
    print(f"Total Pages Pulled From API     : {pages_fetched}")
    print(f"Data Duplicate Ratio            : {duplicate_ratio:.3f}")
    print(f"System Operational Runtime      : {elapsed:.2f} seconds")
    print(f"Pipeline Stream Rate            : {speed:.2f} messages/sec")
    print("="*50)

    # Log operational runs history
    file_exists = log_file.exists()
    with open(log_file, "a", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        if not file_exists:
            writer.writerow([
                "timestamp", "new_records", "duplicates_skipped", 
                "total_bronze_records", "runtime_seconds", 
                "records_per_second", "pages_fetched", "duplicate_ratio"
            ])
        writer.writerow([
            datetime.now().isoformat(), new_records, duplicate_records,
            len(existing_ids), round(elapsed, 2), round(speed, 2),
            pages_fetched, round(duplicate_ratio, 4)
        ])


if __name__ == "__main__":
    main()