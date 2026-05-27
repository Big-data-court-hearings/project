"""Run historical ingestion by year or month windows.

Usage example:
python scripts/run_historical_ingest.py --start-date 2010-01-01 --end-date 2015-12-31 --window year --use-disk-index
"""
import sys
from pathlib import Path
import argparse
import shelve
import json
import time
import csv
from datetime import datetime, date, timedelta

sys.path.append(r'C:/code/courtlistener-project')
from ingestion.api_client import stream_paginated_data
from ingestion.checkpoint import load_checkpoint, save_checkpoint
from ingestion.config import DOCKETS_PATH, MAX_RECORDS, PROJECT_ROOT

ID_INDEX_PATH = PROJECT_ROOT / "logs" / "id_index.db"
HIST_LOG = PROJECT_ROOT / "logs" / "historical_ingestion.csv"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--window", choices=("year", "month"), default="year")
    parser.add_argument("--use-disk-index", action="store_true")
    parser.add_argument("--disable-early-stopping", action="store_true")
    parser.add_argument("--max-records-per-window", type=int, default=None)
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
        if cur.month == 12:
            next_month = date(cur.year + 1, 1, 1)
        else:
            next_month = date(cur.year, cur.month + 1, 1)
        wstart = max(cur, start)
        wend = min(next_month - timedelta(days=1), end)
        yield wstart, wend
        cur = next_month


def ensure_index(db_path: Path, bronze_file: Path):
    """Populate shelve index with existing Bronze IDs if not present."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with shelve.open(str(db_path), writeback=False) as db:
        if len(db) > 0:
            return
        if not bronze_file.exists():
            return
        with open(bronze_file, 'r', encoding='utf-8') as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                    _id = str(row.get('id'))
                    if _id:
                        db[_id] = 1
                except Exception:
                    continue


def run():
    args = parse_args()
    start = datetime.fromisoformat(args.start_date).date()
    end = datetime.fromisoformat(args.end_date).date()
    if args.window == 'year':
        windows = list(year_windows(start, end))
    else:
        windows = list(month_windows(start, end))

    bronze_file = DOCKETS_PATH / 'dockets_raw.jsonl'

    # load checkpoint
    ck = load_checkpoint('dockets')
    ck_date = None
    if ck and isinstance(ck, dict):
        ck_date = ck.get('date')

    # prepare historical log
    hist_exists = HIST_LOG.exists()

    for wstart, wend in windows:
        wstart_iso = wstart.isoformat()
        wend_iso = wend.isoformat()

        # skip windows fully covered by checkpoint
        if ck_date and ck_date >= wend_iso:
            print(f"Skipping window {wstart_iso} to {wend_iso} (covered by checkpoint)")
            continue

        params = {"date_filed__gte": wstart_iso, "date_filed__lte": wend_iso}

        # prepare ID index
        use_shelve = args.use_disk_index
        db = None
        if use_shelve:
            ensure_index(ID_INDEX_PATH, bronze_file)
            db = shelve.open(str(ID_INDEX_PATH), writeback=False)

        else:
            # fallback: load existing IDs into memory (may be large)
            existing_ids = set()
            if bronze_file.exists():
                with open(bronze_file, 'r', encoding='utf-8') as fh:
                    for line in fh:
                        try:
                            row = json.loads(line)
                            existing_ids.add(row.get('id'))
                        except Exception:
                            continue

        window_new = 0
        window_duplicates = 0
        window_processed = 0
        window_pages = 0
        latest_date_seen = None
        latest_id_seen = None
        start_time = time.time()

        with open(bronze_file, 'a', encoding='utf-8') as outfh:
            try:
                stats = {'pages_fetched': 0}
                for row in stream_paginated_data(endpoint='dockets/', max_records=args.max_records_per_window or MAX_RECORDS, params=params, stats=stats):
                    window_processed += 1
                    _id = row.get('id')
                    # check duplicate
                    is_dup = False
                    if use_shelve:
                        if str(_id) in db:
                            is_dup = True
                    else:
                        if _id in existing_ids:
                            is_dup = True

                    if is_dup:
                        window_duplicates += 1
                        continue

                    # write
                    outfh.write(json.dumps(row) + '\n')

                    # update index
                    if use_shelve:
                        db[str(_id)] = 1
                    else:
                        existing_ids.add(_id)

                    window_new += 1

                    # track latest date/id
                    rd = row.get('date_filed')
                    if rd:
                        if latest_date_seen is None or rd > latest_date_seen or (rd == latest_date_seen and str(_id) > (latest_id_seen or '')):
                            latest_date_seen = rd
                            latest_id_seen = str(_id)

                    # periodic checkpoint save
                    if window_new % 1000 == 0 and latest_date_seen:
                        save_checkpoint('dockets', latest_date_seen, latest_id_seen)
                        print(f"Periodic checkpoint saved during window {wstart_iso}: {latest_date_seen} / {latest_id_seen}")

                window_pages = stats.get('pages_fetched', 0)

            except KeyboardInterrupt:
                print('Interrupted during window; saving checkpoint and closing index...')

            finally:
                if use_shelve and db is not None:
                    db.close()

                # save checkpoint for window if progressed
                if latest_date_seen:
                    save_checkpoint('dockets', latest_date_seen, latest_id_seen)
                    print(f"Window checkpoint saved: {latest_date_seen} / {latest_id_seen}")

        elapsed = time.time() - start_time
        throughput = window_new / elapsed if elapsed > 0 else 0
        duplicate_ratio = window_duplicates / window_processed if window_processed > 0 else 0

        # write historical log
        with open(HIST_LOG, 'a', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            if not hist_exists:
                writer.writerow(['timestamp', 'window_start', 'window_end', 'new_records', 'duplicates', 'processed', 'pages_fetched', 'runtime_seconds', 'records_per_second', 'duplicate_ratio'])
                hist_exists = True
            writer.writerow([datetime.now().isoformat(), wstart_iso, wend_iso, window_new, window_duplicates, window_processed, window_pages, round(elapsed,2), round(throughput,2), round(duplicate_ratio,4)])

        print(f"Completed window {wstart_iso} -> {wend_iso}: new={window_new}, dup={window_duplicates}, pages={window_pages}, throughput={throughput:.2f} rec/s")


if __name__ == '__main__':
    run()
