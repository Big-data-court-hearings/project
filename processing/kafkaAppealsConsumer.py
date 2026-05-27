from quixstreams import Application
import os 
import json
import pandas as pd
from pathlib import Path
from datetime import datetime
import logging


today = datetime.today().strftime('%Y-%m-%d_%H-%M-%S')

broker = os.getenv("KAFKA_BROKER", "localhost:9092")
base_path = Path(__file__).parent 
file_path = base_path /".."/"gold"/ "appeals"/f"appeals_{today}.parquet"

def main():
    app = Application(
        broker_address=broker,
        loglevel="DEBUG",
        consumer_group="to_gold",
        auto_offset_reset="earliest"
    )

    with app.get_consumer() as consumer:
        consumer.subscribe(["silver_appeals"])
        while True:
            msg = consumer.poll(1)
            if msg is None:
                print("Waiting...")
            elif msg.error() is not None:
                raise Exception(msg.error())
            else:
                key = msg.key().decode("utf8")
                value =json.loads(msg.value().decode("utf8"))
                df_appeals =pd.DataFrame(value)

                # turn into date type as parquet reads them
                if "date_disposed" in df_appeals.columns:
                    df_appeals["date_disposed"] = pd.to_datetime(df_appeals["date_disposed"], format= "%Y-%m-%d", errors="coerce")
                else:
                    df_appeals["date_disposed"] = pd.NaT
                if "date_filed" in df_appeals.columns:
                    df_appeals["date_filed"] = pd.to_datetime(df_appeals["date_filed"], format= "%Y-%m-%d", errors="coerce")
                else:
                    df_appeals["date_filed"] = pd.NaT
                if "date_judgment" in df_appeals.columns:
                    df_appeals["date_judgment"] = pd.to_datetime(df_appeals["date_judgment"], format= "%Y-%m-%d", errors="coerce")
                else:
                    df_appeals["date_judgment"] = pd.NaT
                if "date_judgment_eod" in df_appeals.columns:
                    df_appeals["date_judgment_eod"] = pd.to_datetime(df_appeals["date_judgment_eod"], format= "%Y-%m-%d", errors="coerce")
                else:
                    df_appeals["date_judgment_eod"] = pd.NaT
                if "date_filed_noa" in df_appeals.columns:
                    df_appeals["date_filed_noa"] = pd.to_datetime(df_appeals["date_filed_noa"], format= "%Y-%m-%d", errors="coerce")
                else: 
                    df_appeals["date_filed_noa"] = pd.NaT
                if "date_received_coa" in df_appeals.columns:
                    df_appeals["date_received_coa"] = pd.to_datetime(df_appeals["date_received_coa"], format= "%Y-%m-%d", errors="coerce")
                else:
                    df_appeals["date_received_noa"] = pd.NaT
                
                offset = msg.offset()
                today = datetime.today().strftime('%Y-%m-%d_%H-%M')
                file_path = base_path /".."/"gold"/ "appeals"/f"appeals_{today}_offset{offset}.parquet"

                df_appeals.to_parquet(file_path,index=False)
                print(f"{file_path} saved to parquet")
                
                print(f"{offset} {key} {value} ")
                # to show ones after already streamed
                consumer.store_offsets(msg)
                consumer.commit(msg)
                logging.info(f"Page sent to gold")



if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    main()
