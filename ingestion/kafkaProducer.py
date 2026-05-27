import requests
from quixstreams import Application
import json
import os
import logging
import time
from datetime import datetime
from pathlib import Path

BASE_PATH = Path(__file__).parent
START_URL = "https://www.courtlistener.com/api/rest/v4/dockets/"
STATE_FILE = BASE_PATH / "last_update_state.txt"

def load_last_update():
    if STATE_FILE.exists():
        with open(STATE_FILE, "r") as f:
            saved_date = f.read().strip()
            if saved_date:
                logging.info(f"Last loading date retrived. Last loading date: {saved_date}")
                return saved_date
    
    default_start = '2026-04-28T09:02:41'
    logging.info(f"No state file found, the program will start from {default_start}")
    return default_start

def save_last_update(new_timestamp):
    # writes new timestamp in state file
    with open(STATE_FILE, "w") as f:
        f.write(new_timestamp)
    logging.info(f"Stato aggiornato e salvato nel file: {new_timestamp}")

def get_dockets(current_url,last_update):
    headers = {'Authorization': f'Token 03aff4672ad061fa70a808bc3e81d802013fa865'}
    before_ts = datetime.today().strftime('%Y-%m-%dT%H:%M:%S')
    try:
        # each page is processed as its own json
        if current_url == START_URL:
            params = {
            'date_modified__gt': last_update, 
            'date_terminated__gte': '2025-01-01'
        }
            response = requests.get(current_url, 
                                headers = headers, 
                                params=params)
        else:
            response = requests.get(current_url, 
                                headers = headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as http_err:
        logging.error(f"HTTP Error from server: {http_err}")
        if response.status_code == 429:
            logging.warning("Good job, you reached the Courtlistener limit, let's hope they won't block you again")
            time.sleep(30)
            raise http_err 
        return None
    except Exception as e:
        logging.error(f"You encountered this error: {e}")
        return None 

def main():
    broker = os.getenv("KAFKA_BROKER", "localhost:9092")
    app = Application(broker_address = broker, 
                      loglevel = "INFO",
                      producer_extra_config={
                        "compression.type": "gzip",    # compressing the json to avoid kafka's memory limit
                        "max.in.flight.requests.per.connection": 1
                    }
        )
    last_update = load_last_update()
    execution_timestamp = datetime.today().strftime('%Y-%m-%dT%H:%M:%S')
    current_page_url = START_URL
    with app.get_producer() as producer:
        while current_page_url:
            logging.info("Fetching data from {}".format(current_page_url))
            stream = get_dockets(current_page_url, last_update)
            if stream is None:
                logging.info("Skipping for bad response")
                time.sleep(15)
                continue
            logging.debug("Got dockets from Courtlistener")
            results = stream.get("results", [])
            # I want to send the full shiz as a json file sooo
            if len(results)>0:
                producer.produce(
                        topic = "bronze",
                        key = "dockets_page",
                        value = json.dumps(results)
                )

                logging.info("Just sent to bronze {} records".format(len(results)))
                last_docket_date = results[0].get("date_modified")
                if last_docket_date:
                    # Puliamo la stringa se contiene millisecondi o la 'Z' finale (es. 2026-05-27T10:15:00Z)
                    clean_date = last_docket_date.split(".")[0].replace("Z", "")
                    
                    save_last_update(clean_date)
                    last_update = clean_date
            current_page_url = stream.get("next") 
            if current_page_url:
                logging.info("Moving to next page. Sleeping 5 seconds to respect rate limits...")
                time.sleep(5)

        producer.flush()
if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    main()
