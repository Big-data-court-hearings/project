from quixstreams import Application
import datetime as dt
import os
import logging 
import json
import pandas as pd

broker = os.getenv("KAFKA_BROKER", "localhost:9092")

def main():
    # first a Consumer fetches data from bronze, which is processed and THEN sent to silver by a Producer
    app = Application(broker_address=broker, 
                    consumer_group="silver_cleaner",
                    auto_offset_reset="earliest")

    with app.get_consumer() as consumer, app.get_producer() as producer:
        consumer.subscribe(["bronze"])
        logging.info("Fetching bronze data ...")
        while True:
            msg = consumer.poll(1)
            if msg is None:
                print("Waiting...")
                continue
            elif msg.error() is not None:
                raise Exception(msg.error())
            page_results = json.loads(msg.value().decode("utf8"))
            if not page_results:
                consumer.store_offsets(msg)
                consumer.commit(msg)
                continue
            logging.info(f"Loading {len(page_results)} records...")
            data_main = []
            data_appeals = []

            # single json in split into two datasets: dockets and appeals
            for line in page_results:
                if line["original_court_info"] != None:
                    line["is_appeal"] = True
                    line["original_court_info"]["parent_docket_number"] = line["original_court_info"]["docket_number"] 
                    del line["original_court_info"]["docket_number"] 
                    line["original_court_info"]["docket_number"] = line["docket_number"]
                    data_appeals.append(line["original_court_info"])
                    del line["original_court_info"]
                    data_main.append(line)
                else:
                    line["is_appeal"] = False
                    del line["original_court_info"]
                    data_main.append(line)
            if len(data_main)>0:
                df_main = pd.DataFrame(data_main)
                # clean df_main (dockets)
                df_main = df_main.reindex(columns=["docket_number","is_appeal","court_id","date_argued", "date_filed", "date_terminated", "date_last_filing","jury_demand", "nature_of_suit", "cause","jurisdiction_type"])
                df_main.loc[(df_main["jury_demand"] == "Plaintiff") | (df_main["jury_demand"] == "Defendant"), "jury_demand"] = True
                df_main.loc[(df_main["jury_demand"] != True) & (df_main["jury_demand"] != None), "jury_demand"] = False
                dockets = df_main.to_json(orient="records")
                producer.produce(
                topic="silver_dockets",
                    key="docket",
                    value=dockets
                )
                logging.info(f"Dockets sent to silver_dockets")
            if len(data_appeals) > 0:
                # clean df_appeals
                df_appeals = pd.DataFrame(data_appeals)
                
                df_appeals = df_appeals.drop(columns=['resource_uri', 'id', 'date_created', 'date_modified',
                    'docket_number_raw', 'assigned_to_str', 'ordering_judge_str',
                    'court_reporter', 'assigned_to', 'ordering_judge', "date_rehearing_denied"], errors ="ignore")
                # set to json
                
                appeals = df_appeals.to_json(orient="records")
                # each dataframe in sent to a different topic 
                
                producer.produce(
                    topic="silver_appeals",
                        key="docket",
                        value=appeals
                )
                logging.info(f"Appeals sent to silver_appeals")
            producer.flush()
            consumer.store_offsets(msg)
            consumer.commit(msg)
            

if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    main()