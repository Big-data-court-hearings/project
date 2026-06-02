"""
This script accesses with Kafka the bronze data, then cleans them, 
processes them, and stores them in a parquet file.
It automatically shuts down if no new messages are received for one minute.
"""

from quixstreams import Application
import os
import json
import time  # Need time to track timeouts
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path

broker = os.getenv("KAFKA_BROKER", "localhost:9092")
base_path = Path(__file__).parent 

# Timeout configuration (in seconds)
IDLE_TIMEOUT_SECONDS = 20 

def calculate_activity_ranges(row):
    """
    Calcola le liste degli anni e dei trimestri di attività per ogni riga.
    Formatta i trimestri esattamente come 'YYYY-qX' (es. '2026-q1').
    Se date_terminated è nullo, estende il calcolo fino al trimestre attuale (giugno 2026).
    """
    if pd.isnull(row["date_filed"]):
        return [], []
        
    start_date = row["date_filed"]
    # Se la causa è attiva, usiamo il timestamp corrente (giugno 2026)
    end_date = row["date_terminated"] if pd.notnull(row["date_terminated"]) else pd.Timestamp(datetime.now())
    
    if start_date > end_date:
        return [], []

    # 1. Calcolo degli anni di attività
    years = [str(y) for y in range(start_date.year, end_date.year + 1)]
    
    # 2. Calcolo dei trimestri di attività con formattazione nativa Pandas 'YYYY-qX'
    quarter_range = pd.date_range(
        start=start_date.to_period('Q').start_time,
        end=end_date.to_period('Q').start_time,
        freq='QS'
    )
    # dt.to_period('Q') restituisce qualcosa come '2026Q1'. Lo convertiamo in '2026-q1'
    quarters = [str(dt.to_period('Q')).lower().replace('q', '-q') for dt in quarter_range]
    
    return years, quarters

def main():
    app = Application(
        broker_address=broker, 
        consumer_group="silver_cleaner",
        auto_offset_reset="earliest"
    )

    with app.get_consumer() as consumer:
        consumer.subscribe(["bronze"])
        print("Fetching bronze data ...")
        
        # Initialize the idle timer right before entering the consumption loop
        last_message_time = time.time()
        
        while True:
            msg = consumer.poll(1)
            
            if msg is None:
                # Calculate how long the consumer has been sitting idle
                idle_duration = time.time() - last_message_time
                
                
                print("Waiting...")
                continue
                
            elif msg.error() is not None:
                raise Exception(msg.error())
            
            # Reset the idle timer as soon as a valid message is picked up
            last_message_time = time.time()
            
            page_results = json.loads(msg.value().decode("utf8"))
            if not page_results:
                consumer.store_offsets(msg)
                consumer.commit(msg)
                continue
                
            print(f"Loading {len(page_results)} records...")
            offset = msg.offset()
            
            today = datetime.today().strftime('%Y-%m-%dT%H%M%S')
            
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

            # 🚀 Logica di calcolo degli intervalli temporali nel formato corretto
            activity_res = df_clean.apply(calculate_activity_ranges, axis=1)
            df_clean["activity_years"] = [res[0] for res in activity_res]
            df_clean["activity_quarters"] = [res[1] for res in activity_res]

            # 3. 🏅 CONVERT TO STRICT STANDARD ISO STRINGS (%Y-%m-%d)
            date_cols = ["date_filed", "date_terminated", "date_last_filing"]
            for col in date_cols:
                df_clean[col] = df_clean[col].apply(
                    lambda x: x.strftime("%Y-%m-%d") if pd.notnull(x) else None
                )
            
            # Formats your tracking metadata safely as an ISO timestamp sequence
            df_clean["date_modified"] = df_clean["date_modified"].apply(
                lambda x: x.strftime("%Y-%m-%d %H:%M:%S") if pd.notnull(x) else None
            )

            # FIX: Corrected boolean logic filter condition for is_appeal column
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

            file_path = base_path / ".." / "silver" / f"dockets_{today}_offset{offset}.parquet"
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Salvataggio con PyArrow delle liste strutturate
            df_clean.to_parquet(file_path, engine="pyarrow", index=False)
            print(f"Cleaned batch successfully saved to: {file_path.name}")
            
            consumer.store_offsets(msg)
            consumer.commit(msg)
            
    print("Consumer engine stopped safely.")

            
if __name__ == "__main__":
    main()