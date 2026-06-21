"""
Incremental page-by-page docket ingestion script with Kafka streaming.

Downloads docket data from CourtListener API based on time modifications
and streams raw data blocks page-by-page directly to the Kafka Bronze layer.
Seen IDs are checkpointed to disk after every shipped page for fault
tolerance, and run history is logged to a local CSV.
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
from quixstreams.models.topics import TopicAdmin

from ingestion.api_client import stream_paginated_data
from ingestion.config import MAX_RECORDS

# Tracking paths
log_file = PROJECT_ROOT / "logs" / "ingestion_history.csv"

# the API will look for dockets modified before this given number of hours 
HOURS = 8

# If True, obtain_date() will resume from the timestamp of the last
# successful run (LAST_UPDATE_FILE) instead of always using "now - HOURS".
# Currently disabled: kept as a tracked value for future use, but not
# yet relied upon for determining the ingestion window.
USE_LAST_UPDATE = False

SEEN_IDS_FILE = PROJECT_ROOT / "logs" / "seen_ids.json"
LAST_UPDATE_FILE = PROJECT_ROOT / "logs" / "last_update.json"

def load_seen_ids():
    if SEEN_IDS_FILE.exists():
        with open(SEEN_IDS_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_seen_ids(seen_ids):
    SEEN_IDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SEEN_IDS_FILE, "w") as f:
        json.dump(list(seen_ids), f)

def load_last_update():
    if LAST_UPDATE_FILE.exists():
        with open(LAST_UPDATE_FILE, "r") as f:
            return json.load(f).get("last_update")
    return None

def save_last_update(timestamp: str):
    LAST_UPDATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LAST_UPDATE_FILE, "w") as f:
        json.dump({"last_update": timestamp}, f)

def parse_args():
    parser = argparse.ArgumentParser(description="Ingest dockets to Kafka page-by-page")
    parser.add_argument("--start-date", help="Start date (YYYY-MM-DD) for historical ingestion")
    return parser.parse_args()


def obtain_date():
    """Fallback in case --start-date isn't provided.

    If USE_LAST_UPDATE is enabled and a previous run's timestamp is
    available, resume from there. Otherwise, default to "now - HOURS".
    """
    if USE_LAST_UPDATE:
        last_update = load_last_update()
        if last_update:
            print(f"Resuming from last recorded update: {last_update}")
            return last_update

    default = (datetime.today() - timedelta(hours=HOURS)).strftime('%Y-%m-%dT%H:%M:%S')
    print(f"No specific date provided. Default will be used: {default}")
    return default

delivery_errors = []

def _on_delivery(err, msg):
    """Raise if Kafka fails to deliver a produced message, so we never mark
    a page's IDs as 'seen' unless it actually landed on the broker."""
    if err is not None:
        delivery_errors.append(str(err))
        raise RuntimeError(f"Kafka delivery failed: {err}")

def main():
    args = parse_args()
    
    # Setup QuixStreams Application Infrastructure
    broker = os.getenv("KAFKA_BROKER", "localhost:9092")
    app = Application(
        broker_address=broker,
        loglevel="WARNING",
        producer_extra_config={
            "compression.type": "gzip",
            "max.in.flight.requests.per.connection": 1
        }
    )

    print("Verifying Kafka topic availability...")
    
    # Define your topic parameters using QuixStreams
    bronze_topic = app.topic(name="bronze", value_serializer="json")
    
    # Instantiate the administrator directly
    admin = TopicAdmin(broker_address=broker)
    try:
        existing_topics = admin.list_topics()
        if "bronze" not in existing_topics:
            print("Topic [bronze] not found. Initiating creation...")
            admin.create_topics([bronze_topic])
            print("Topic [bronze] successfully created on the broker.")
        else:
            print("Topic [bronze] verified on broker. Skipping creation step.")
    except Exception as e:
        print(f"Non-fatal warning checking topics: {e}")

    start_time = time.time()
    new_records = 0

    if args.start_date:
        last_update = args.start_date
    else:
        last_update = obtain_date()

    params = None
    if last_update:
        params = {"date_modified__gt": last_update}
    
    stats = {"pages_fetched": 0}

    print("Initializing connection to Kafka topic: [bronze]...")

    with app.get_producer() as producer:
        try:
            page_buffer = []
            last_page_count = 0
            duplicates_skipped = 0
            seen_ids = load_seen_ids()
            for row in stream_paginated_data(
                endpoint="dockets/",
                max_records=MAX_RECORDS,
                params=params,
                stats=stats
            ):
                record_id = row.get("id")  # <-- adatta al nome del campo ID della tua API
    
                current_page_count = stats.get("pages_fetched", 1)
                if record_id and record_id in seen_ids:
                    duplicates_skipped += 1
                    continue
                
                # ─── PAGE BOUNDARY DETECTOR ──────────────────────────────────────
                # If the API client flipped to a new page, ship the buffered page out 
                if current_page_count != last_page_count and page_buffer:
                    producer.produce(
                        topic="bronze",
                        key=f"page_{last_page_count}",
                        value=json.dumps(page_buffer),
                        on_delivery=_on_delivery
                    )
                    producer.poll(0)
                    print(f"Shipped page batch {last_page_count} with {len(page_buffer)} records to Kafka.")
                    new_records += len(page_buffer)

                    # Checkpoint: persist seen IDs for this page immediately, so a
                    # crash later only risks re-doing the current (in-flight) page.
                    page_ids = {r.get("id") for r in page_buffer if r.get("id")}
                    seen_ids.update(page_ids)
                    save_seen_ids(seen_ids)

                    page_buffer = []  # Clear memory for the next page array
                
                last_page_count = current_page_count

                # Accumulate row item into current active page list directly
                page_buffer.append(row)

            # ─── FINAL CLEANUP SHIPMENT ──────────────────────────────────────
            # Don't leave any leftover records sitting in the last page buffer
            if page_buffer:
                producer.produce(
                    topic="bronze",
                    key=f"page_{last_page_count}",
                    value=json.dumps(page_buffer),
                    on_delivery=_on_delivery
                )
                producer.poll(0)
                print(f"Shipped final page batch {last_page_count} with {len(page_buffer)} records to Kafka.")
                new_records += len(page_buffer)

                page_ids = {r.get("id") for r in page_buffer if r.get("id")}
                seen_ids.update(page_ids)
                save_seen_ids(seen_ids)

        except KeyboardInterrupt:
            print("\nExecution halted by operator command.")
        finally:
            # Flush pipeline out to cluster brokers safely
            producer.flush()
        if delivery_errors:
            print(f"WARNING: {len(delivery_errors)} pages failed delivery")

    # ============================================================
    # PIPELINE METRICS SUMMARY
    # ============================================================
    elapsed = time.time() - start_time
    speed = new_records / elapsed if elapsed > 0 else 0
    pages_fetched = stats.get("pages_fetched", 0)

    # Track this run's timestamp for potential future resumption.
    # Not yet consumed unless USE_LAST_UPDATE is enabled (see obtain_date()).
    save_last_update(datetime.now().strftime('%Y-%m-%dT%H:%M:%S'))

    # Log operational runs history
    file_exists = log_file.exists()
    with open(log_file, "a", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        if not file_exists:
            writer.writerow([
                "timestamp", "new_records", "duplicates_skipped", 
                "runtime_seconds", 
                "records_per_second", "pages_fetched", "duplicate_ratio"
            ])
        writer.writerow([
            datetime.now().isoformat(), new_records, duplicates_skipped,  
            round(elapsed, 2), round(speed, 2),
            pages_fetched, round(duplicates_skipped / (new_records + duplicates_skipped), 4) if (new_records + duplicates_skipped) > 0 else 0.0
        ])


if __name__ == "__main__":
    main()