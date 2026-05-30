"""
This script accesses with Kafka the bronze data, then cleans them, 
processes them, and stores them in a parquet file.
It automatically shuts down if no new messages are received for 3 minutes.
"""

from quixstreams import Application
import os
import json
import time  # Need time to track timeouts
import pandas as pd
from datetime import datetime
from pathlib import Path

broker = os.getenv("KAFKA_BROKER", "localhost:9092")
base_path = Path(__file__).parent 

# Timeout configuration (2 minutes = 120 seconds)
IDLE_TIMEOUT_SECONDS = 120

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
                
                if idle_duration >= IDLE_TIMEOUT_SECONDS:
                    print(f"🛑 No new data received for {int(idle_duration)} seconds. Initiating graceful shutdown.")
                    break
                
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
            
            # Fixed: Using dashes/seconds instead of colons (:) so Windows paths don't crash
            today = datetime.today().strftime('%Y-%m-%dT%H%M%S')
            
            df = pd.DataFrame(page_results)
            df_clean = df.reindex(columns=[
                "id", "court_id", "case_name", "date_filed", 
                "date_terminated", "date_last_filing", "nature_of_suit", 
                "cause", "jurisdiction_type", "blocked", "source", "date_modified"
            ])
            
            # Fixed: Removed format='%Y-%m-%d' restriction to prevent complete data erasure on timestamp values
            date_cols = ["date_filed", "date_terminated", "date_last_filing", "date_modified"]
            for col in date_cols:
                df_clean[col] = pd.to_datetime(df_clean[col], errors="coerce")
                
            df_clean = df_clean.dropna(subset=["id", "date_filed", "date_modified"], how="any")
            
            if df_clean.empty:
                print("Batch empty after filter operations. Skipping save.")
                consumer.store_offsets(msg)
                consumer.commit(msg)
                continue

            file_path = base_path / ".." / "silver" / f"dockets_{today}_offset{offset}.parquet"
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            df_clean.to_parquet(file_path, engine="pyarrow", index=False)
            print(f"✅ Cleaned batch successfully saved to: {file_path.name}")
            
            consumer.store_offsets(msg)
            consumer.commit(msg)
            
    print("Consumer engine stopped safely.")

            
if __name__ == "__main__":
    main()