import requests
import json
import time

# Configuration
TOKEN = '03aff4672ad061fa70a808bc3e81d802013fa865'
BASE_URL = "https://www.courtlistener.com/api/rest/v4/dockets/"
TARGET_COUNT = 100

def fetch_dockets(limit=100):
    headers = {'Authorization': f'Token {TOKEN}'}
    # Filtering for records filed before Jan 1st, 2025
    params = {'date_filed__lt': '2025-01-01'} 
    
    all_records = []
    next_url = BASE_URL
    
    print(f"Fetching {limit} records published before 2025...")

    while next_url and len(all_records) < limit:
        try:
            # We only pass params on the first call; 
            # subsequent 'next' URLs already contain the filter
            response = requests.get(next_url, headers=headers, params=params if next_url == BASE_URL else None)
            
            if response.status_code == 429:
                print("Rate limit hit. Sleeping...")
                time.sleep(5)
                continue
                
            response.raise_for_status()
            data = response.json()
            
            batch = data.get('results', [])
            
            # Since we filtered via the URL, we can just extend the list
            all_records.extend(batch)
            
            print(f"Collected {len(all_records)} records...")
            next_url = data.get('next')
            
        except requests.exceptions.RequestException as e:
            print(f"Error: {e}")
            break

    return all_records[:limit]

if __name__ == "__main__":
    records = fetch_dockets(TARGET_COUNT)
    
    with open("courtlistener_dockets.json", "w") as f:
        json.dump(records, f, indent=4)
        
    print(f"\nSuccess! Saved {len(records)} records to courtlistener_dockets.json")