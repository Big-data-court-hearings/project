from quixstreams import Application
import os 
import json
import pandas as pd
from pathlib import Path
from datetime import datetime
import logging




broker = os.getenv("KAFKA_BROKER", "localhost:9092")
base_path = Path(__file__).parent 

def main():
    app = Application(
        broker_address=broker,
        loglevel="DEBUG",
        consumer_group="to_gold",
        auto_offset_reset="earliest"
    )

    with app.get_consumer() as consumer:
        consumer.subscribe(["silver_dockets"])
        while True:
            msg = consumer.poll(1)
            if msg is None:
                print("Waiting...")
            elif msg.error() is not None:
                raise Exception(msg.error())
            else:
                key = msg.key().decode("utf8")
                value =json.loads(msg.value().decode("utf8"))
                df_main =pd.DataFrame(value)
                offset = msg.offset()
                # set as dates as Parquet reads them (unlike json)
                df_main["date_argued"] = pd.to_datetime(df_main["date_argued"], format= "%Y-%m-%d", errors="coerce")
                df_main["date_filed"] = pd.to_datetime(df_main["date_filed"], format= "%Y-%m-%d", errors="coerce")
                df_main["date_terminated"] = pd.to_datetime(df_main["date_terminated"], format= "%Y-%m-%d", errors="coerce")
                df_main["date_last_filing"] = pd.to_datetime(df_main["date_last_filing"], format= "%Y-%m-%d", errors="coerce")
                today = datetime.today().strftime('%Y-%m-%d_%H-%M')
                file_path = base_path /".."/"gold"/ "dockets"/f"dockets_{today}_offset{offset}.parquet"
                df_main.to_parquet(file_path,index=False)
                print(f"{file_path} saved to parquet")
                print(f"{offset} {key} {value} ")
                # to show ones after already streamed
                consumer.store_offsets(msg)
                consumer.commit(msg)
                logging.info(f"Page sent to gold")



if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    main()
