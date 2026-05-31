"""This script uses Gemini and the court database to classify 
all the active courts in the US listed on Courtlistener"""


import os
import time
from pathlib import Path
from typing import List, Optional
import pandas as pd
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from dotenv import load_dotenv

base_path = Path(__file__).parent 
file_path = base_path / ".." / "silver" / "courts" / "courts_classified.parquet"
file_path.parent.mkdir(parents=True, exist_ok=True) # Ensure directory exists

load_dotenv()

API_TOKEN = os.getenv("GEMINI_TOKEN")
client = genai.Client(api_key = API_TOKEN)

df = pd.read_csv('courts-2026-03-31.csv')
active_courts = df[df['in_use'] == 't']
print(f"Total active courts to process: {len(active_courts)}")

all_classified_courts = []
chunk_size = 50 
level_list = ["district", "bankruptcy", "appellate", "bankruptcy_appellate", "special", "administrative", "state"]

class Court(BaseModel):
    court_id: str = Field(description="'id' in the csv file")
    name: str = Field(description="'full_name' in the csv file")
    jurisdiction: str = Field(description="'jurisdiction' in the csv file, 'S' in place of NaN")
    level: str = Field(description=f"Classification from {level_list}, use 'special' instead of NaN or null")
    is_federal: bool = Field(description="True if federal, else False")
    district_id: Optional[str] = Field(default=None, description="District ID or null")
    district_name: Optional[str] = Field(default=None, description="District name or null")
    circuit: str = Field(description="Circuit number or 20")
    
class CourtList(BaseModel):
    courts: List[Court]

try:
    for i in range(0, len(active_courts), chunk_size):
        chunk = active_courts.iloc[i : i + chunk_size]
        csv_string = chunk.to_csv(index=False)
        
        print(f"Processing rows {i} to {i + len(chunk)}...")
        
        prompt = f"Classify these active courts into JSON according to the schema:\n{csv_string}"
        success = False
        retries = 0
        
        while not success and retries < 5:
            try:
                response = client.models.generate_content(
                    model="gemini-2.5-flash",  
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=CourtList,
                    ),
                )
                
                # Validate and parse
                batch = CourtList.model_validate_json(response.text)
                all_classified_courts.extend(batch.model_dump()['courts'])
                success = True
                time.sleep(2) # Slight courtesy pause between chunks
                
            except Exception as e:
                retries += 1
                if "429" in str(e):
                    print(f"Rate limit hit. Waiting 60 seconds to reset (Attempt {retries}/5)...")
                    time.sleep(60) 
                elif "503" in str(e):
                    wait = (2 ** retries) 
                    print(f"Server busy, retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    print(f"Unexpected error at chunk starting at {i}: {e}")
                    # Decide if you want to skip or break. Breaking safely retains data gathered so far.
                    break 

finally:
    if all_classified_courts:
        print(f"Saving {len(all_classified_courts)} processed records to Parquet...")
        output_df = pd.DataFrame(all_classified_courts)
        output_df.to_parquet(file_path, engine="pyarrow")
    else:
        print("No records were successfully processed.")