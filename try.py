import requests
import json
import time

# Configuration
TOKEN = '03aff4672ad061fa70a808bc3e81d802013fa865'
BASE_URL = "https://www.courtlistener.com/api/rest/v4/dockets/"
TARGET_COUNT = 100

def fetch_dockets(limit=100):
    headers = {'Authorization': f'Token {TOKEN}'}
    all_records = []
    next_url = BASE_URL
    
    print(f"Fetching {limit} records...")

    while next_url and len(all_records) < limit:
        try:
            response = requests.get(next_url, headers=headers)
            
            # Handle rate limiting (429)
            if response.status_code == 429:
                print("Rate limit hit. Sleeping for 5 seconds...")
                time.sleep(5)
                continue
                
            response.raise_for_status()
            data = response.json()
            
            # Add the results from this page to our main list
            batch = data.get('results', [])
            all_records.extend(batch)
            
            print(f"Collected {len(all_records)} records...")

            # Get the next page URL from the API metadata
            next_url = data.get('next')
            
        except requests.exceptions.RequestException as e:
            print(f"Error: {e}")
            break

    # Trim to exactly the limit requested
    return all_records[:limit]

if __name__ == "__main__":
    records = fetch_dockets(TARGET_COUNT)
    
    # Save or print the results
    with open("courtlistener_dockets.json", "w") as f:
        json.dump(records, f, indent=4)
        
    print(f"\nSuccess! Saved {len(records)} records to courtlistener_dockets.json")