from google import genai
from google.genai import types
import time
from pydantic import BaseModel, Field
from typing import List
import pandas as pd
from pathlib import Path

base_path = Path(__file__).parent 
file_path = base_path / ".." / "bronze" / "bronze_courts_classified.parquet"

client = genai.Client(api_key='AIzaSyBNI1MaG1_H1Ku12q70KSeFtHvPt1lbW44')

df = pd.read_csv('courts-2026-03-31.csv')
active_courts = df[df['in_use'] == 't']
print(f"Total active courts to process: {len(active_courts)}")
all_classified_courts = []
chunk_size = 50 



level_list = ["district", "bankruptcy", "appellate", "bankruptcy_appellate", "special", "administrative", "state"]
class Court(BaseModel):
    court_id: str = Field(description="'id' in the csv file")
    name: str = Field(description="'full_name' in the csv file")
    jurisdiction: str = Field(description="'jurisdiction' in the csv file")
    level: str = Field(description=f"Classification from {level_list}")
    is_federal: bool = Field(description="True if federal, else False")
    district_id: str = Field(description="District ID or null")
    district_name: str = Field(description="District name or null")
    circuit: str = Field(description="Circuit number or null")
    state: str = Field(description="Federal State in which the court is located")
    
class CourtList(BaseModel):
    courts: List[Court]



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
                model="gemini-3-flash-preview",
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": CourtList,
                },
            )
            # Validate and add to our master list
            batch = CourtList.model_validate_json(response.text)
            all_classified_courts.extend(batch.model_dump()['courts'])
            success = True
            time.sleep(10)
        except Exception as e:
            if "429" in str(e):
                print(f"Rate limit hit. Waiting 60 seconds to reset...")
                time.sleep(60) 
                retries += 1
                if retries > 5:
                    break
            elif "503" in str(e):
                wait = (2 ** retries) 
                print(f"Server busy, retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"Failed chunk starting at {i}: {e}")
                break 

df = pd.DataFrame(all_classified_courts)
df.to_parquet(file_path, engine="pyarrow")