"""
Classifies all active US courts from CourtListener.
Saves progress locally so it can be safely interrupted and restarted for free.
NB. Used with a Pro Gemini account, free tier may take several days
"""

import os
import re
import time
from pathlib import Path
from typing import List, Optional

import pandas as pd
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from google.genai.errors import APIError
from dotenv import load_dotenv

# Path setup pointing up to silver directory
base_path = Path(__file__).parent 
file_path = base_path / ".." / "silver" / "courts" / "courts_classified.parquet"
file_path.parent.mkdir(parents=True, exist_ok=True)

load_dotenv()
API_TOKEN = os.getenv("GEMINI_TOKEN") or os.getenv("GEMINI_API_KEY")
if not API_TOKEN:
    raise ValueError("CRITICAL: Missing GEMINI_TOKEN in your .env file.")

client = genai.Client(api_key=API_TOKEN)

# ============================================================
# 1. DETERMINISTIC CIRCUIT LOOKUP FOR FEDERAL COURTS
# ============================================================
COURT_TO_CIRCUIT = {
    "ca1": "1", "ca2": "2", "ca3": "3", "ca4": "4", "ca5": "5",
    "ca6": "6", "ca7": "7", "ca8": "8", "ca9": "9", "ca10": "10",
    "ca11": "11", "cadc": "dc", "cafc": "fc", "bap1": "1", "bap2": "2",
    "bap6": "6", "bap8": "8", "bap9": "9", "bap10": "10", "med": "1",
    "mad": "1", "nhd": "1", "rid": "1", "prd": "1", "ctd": "2",
    "nyed": "2", "nynd": "2", "nysd": "2", "nywd": "2", "vtd": "2",
    "ded": "3", "njd": "3", "paed": "3", "pamd": "3", "pawd": "3",
    "vid": "3", "mdd": "4", "nced": "4", "ncmd": "4", "ncwd": "4",
    "scd": "4", "vaed": "4", "vawd": "4", "wvnd": "4", "wvsd": "4",
    "laed": "5", "lamd": "5", "lawd": "5", "msnd": "5", "mssd": "5",
    "txed": "5", "txnd": "5", "txsd": "5", "txwd": "5", "kyed": "6",
    "kywd": "6", "mied": "6", "miwd": "6", "ohnd": "6", "ohsd": "6",
    "tned": "6", "tnmd": "6", "tnwd": "6", "ilcd": "7", "ilnd": "7",
    "ilsd": "7", "innd": "7", "insd": "7", "wied": "7", "wiwd": "7",
    "ared": "8", "arwd": "8", "iand": "8", "iasd": "8", "mnd": "8",
    "moed": "8", "mowd": "8", "ned": "8", "ndd": "8", "sdd": "8",
    "akd": "9", "azd": "9", "cacd": "9", "caed": "9", "cand": "9",
    "casd": "9", "gud": "9", "hid": "9", "idd": "9", "mtd": "9",
    "nvd": "9", "nmid": "9", "ord": "9", "waed": "9", "wawd": "9",
    "cod": "10", "ksd": "10", "nmd": "10", "oked": "10", "oknd": "10",
    "okwd": "10", "utd": "10", "wyd": "10", "almd": "11", "alnd": "11",
    "alsd": "11", "flmd": "11", "flnd": "11", "flsd": "11", "gamd": "11",
    "gand": "11", "gasd": "11", "dcd": "dc", "scotus": "20"
}

def get_circuit(court_id: str) -> Optional[str]:
    cid = str(court_id).lower().strip()
    # Handle bankruptcy suffix variations safely
    if cid.endswith("b") and cid[:-1] in COURT_TO_CIRCUIT:
        return COURT_TO_CIRCUIT[cid[:-1]]
    return COURT_TO_CIRCUIT.get(cid)

# ============================================================
# 2. SCHEMAS
# ============================================================
level_list = ["district", "bankruptcy", "appellate", "bankruptcy_appellate", "special", "administrative", "state"]

class Court(BaseModel):
    court_id: str = Field(description="'id' in the csv file")
    name: str = Field(description="'full_name' in the csv file")
    jurisdiction: str = Field(description="'jurisdiction' in the csv file; use 'S' if NaN")
    level: str = Field(description=f"Must be one of {level_list}")
    is_federal: bool
    district_id: Optional[str] = None
    district_name: Optional[str] = None
    circuit: str

class CourtList(BaseModel):
    courts: List[Court]

# ============================================================
# 3. PROCESSING PIPELINE
# ============================================================
df = pd.read_csv('courts-2026-03-31.csv')
active_courts = df[df['in_use'] == 't'].copy()
print(f"Total active courts to process: {len(active_courts)}")

# Split out what we can process instantly for free without AI
active_courts["_known_circuit"] = active_courts["id"].apply(get_circuit)
known_courts = active_courts[active_courts["_known_circuit"].notna()].copy()
unknown_courts = active_courts[active_courts["_known_circuit"].isna()].copy()

print(f"  ⚡ Local Lookup (Instant & Free): {len(known_courts)}")
print(f"  🤖 Needs Gemini (State/Other): {len(unknown_courts)}")

# --- CACHE CHECK (The State Saver) ---
existing_progress = []
processed_ids = set()
if file_path.exists():
    try:
        cache_df = pd.read_parquet(file_path)
        existing_progress = cache_df.to_dict(orient="records")
        processed_ids = set(cache_df["court_id"].unique())
        print(f"🔄 Cache detected! Loaded {len(processed_ids)} already processed records.")
    except Exception:
        print("⚠️ Failed reading existing file. Starting clean run.")

# Filter out anything we already completed in a prior run
unknown_filtered = unknown_courts[~unknown_courts["id"].str.lower().isin(processed_ids)].copy()
print(f"🎯 Net remaining courts requiring Gemini processing: {len(unknown_filtered)}")

all_classified_courts = list(existing_progress)
CHUNK_SIZE = 2  # Safe, micro-pacing payload size for free tier tokens
request_count = 0

try:
    for i in range(0, len(unknown_filtered), CHUNK_SIZE):
        chunk = unknown_filtered.iloc[i : i + CHUNK_SIZE]
        csv_string = chunk.to_csv(index=False)
        
        print(f"Gemini: Processing rows {i} to {i + len(chunk)} (Request {request_count + 1})...")
        prompt = f"Classify these active state courts into JSON according to the schema. Set circuit to '20' for state systems:\n{csv_string}"
        
        success = False
        retries = 0
        while not success:
            try:
                response = client.models.generate_content(
                    model="gemini-2.5-flash",  
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=CourtList,
                    ),
                )
                batch = CourtList.model_validate_json(response.text)
                all_classified_courts.extend(batch.model_dump()['courts'])
                success = True
                request_count += 1
                time.sleep(4) # Steady pace delay
                
            except APIError as e:
                retries += 1
                err_msg = str(e)
                if "Quota exceeded" in err_msg or e.code in [429, 503]:
                    match = re.search(r"Please retry in ([\d\.]+)s", err_msg)
                    if match:
                        wait_time = float(match.group(1)) + 2.0
                        print(f"   [Quota Wall Hit] Waiting exactly {wait_time:.2f}s for bucket reset...")
                        time.sleep(wait_time)
                    else:
                        fallback = (2 ** retries) + 15
                        print(f"   [Rate Limit Hit] Sleeping for {fallback}s...")
                        time.sleep(fallback)
                else:
                    print(f"   Unexpected API error: {e}. Retrying chunk in 10s...")
                    time.sleep(10)
            except Exception as e:
                print(f"   Connection anomaly: {e}. Retrying chunk in 10s...")
                time.sleep(10)

finally:
    # Append the instant federal lookup rows that we skipped processing via API
    print("\nAdding local deterministic federal lookups...")
    for _, row in known_courts.iterrows():
        cid = str(row["id"]).lower().strip()
        if cid not in processed_ids:
            # Dynamically infer federal levels based on prefixes
            level = "district"
            if cid.startswith("ca"): level = "appellate"
            elif cid.endswith("b"): level = "bankruptcy"
            elif cid.startswith("bap"): level = "bankruptcy_appellate"
            
            all_classified_courts.append({
                "court_id": cid,
                "name": row.get("full_name", ""),
                "jurisdiction": row.get("jurisdiction", "S") or "S",
                "level": level,
                "is_federal": True,
                "district_id": None,
                "district_name": None,
                "circuit": str(row["_known_circuit"])
            })

    if all_classified_courts:
        print(f"Saving a total of {len(all_classified_courts)} items to Parquet...")
        output_df = pd.DataFrame(all_classified_courts)
        output_df["court_id"] = output_df["court_id"].str.lower()
        # Drop duplicates just in case overlap occurred during an interrupt
        output_df = output_df.drop_duplicates(subset=["court_id"], keep="first")
        output_df.to_parquet(file_path, engine="pyarrow")
        print(f"Done! Clean output generated at: {file_path}")