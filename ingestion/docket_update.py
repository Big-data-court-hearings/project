import requests
import json
import time
from pathlib import Path

# Configuration
TOKEN = '03aff4672ad061fa70a808bc3e81d802013fa865'
BASE_URL = "https://www.courtlistener.com/api/rest/v4/dockets/"

LAST_UPDATE = '2026-05-11T07:02:41'

def fetch_and_save_dockets(file_path):
    headers = {'Authorization': f'Token {TOKEN}'}
    # Ensure date is a string YYYY-MM-DD
    params = {
        'date_modified__gt': LAST_UPDATE, 
        'date_terminated__gt': '2025-01-01'
    } 
    
    next_url = BASE_URL

    with open(file_path, "w") as f:
        while next_url:
            try:
                # Use params ONLY on the first call; next_url already contains them
                response = requests.get(next_url, headers=headers, params=params if next_url == BASE_URL else None)
                
                if response.status_code == 429:
                    print("Rate limit hit. Sleeping 10s...")
                    time.sleep(10)
                    continue
                
                response.raise_for_status()
                data = response.json()
                batch = data.get('results', [])
                
                for record in batch:
                    f.write(json.dumps(record) + "\n")
                
                print(f"Saved batch of {len(batch)} records...")
                
                next_url = data.get('next')
                time.sleep(0.5) 
                
            except requests.exceptions.RequestException as e:
                print(f"Error: {e}")
                break

if __name__ == "__main__":
    base_path = Path(__file__).parent 
    file_path = base_path / ".." / "data" / "raw_json" / "latest_docket_update.jsonl" # Changed to .jsonl
    
    file_path.parent.mkdir(parents=True, exist_ok=True)
    fetch_and_save_dockets(file_path)
    print(f"\nUpdate complete.")