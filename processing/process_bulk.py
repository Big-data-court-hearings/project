import json
import pandas as pd
from pathlib import Path
import csv 
import numpy as np

base_path = Path(__file__).parent 

file_path = base_path /".."/"data"/ "raw_json"/"dockets_terminated_25_onwards.jsonl"

data = []

with open(file_path, 'r', encoding='utf-8') as f:
    for i, line in enumerate(f):
        if line.strip(): # Skip empty lines
            try:
                data.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"Error on line {i+1}")

df = pd.DataFrame(data)
df_clean = df.reindex(columns=
                                  [ "id",
                                    "court_id",
                                    "case_name",
                                    "date_filed",
                                    "date_terminated",
                                    "date_last_filing",
                                    "nature_of_suit",
                                    "cause",
                                    "jurisdiction_type",
                                    "blocked",
                                    "source",
                                    "date_modified"
                                ])
date_cols = ["date_filed","date_terminated","date_last_filing"]
for col in date_cols:
    df_clean[col] = pd.to_datetime(df_clean[col], errors="coerce")
df_clean["date_modified"] = pd.to_datetime(df_clean["date_modified"], errors="coerce")
df_clean=df_clean.dropna(subset=["id","date_filed", "date_terminated", "date_modified"], how ="any")
earliest_case = df_clean.loc[:, "date_filed"].min()
print("EARLIEST CASE", earliest_case)
latest_case = df_clean.loc[:, "date_filed"].max()
print("LATEST CASE", latest_case)

df_clean.to_parquet(base_path /".."/"silver"/ "database_dockets.parquet", engine="pyarrow")

