import json
import pandas as pd
from pathlib import Path
import csv 
import numpy as np

base_path = Path(__file__).parent 

file_path = base_path /".."/"data"/ "raw_json"/"dockets_terminated_25_onwards.jsonl"
file_path2 = base_path /".."/"originating-court-information-2026-03-31.csv"

# load jsonl into DF

data = []

with open(file_path, 'r', encoding='utf-8') as f:
    for i, line in enumerate(f):
        if line.strip(): # Skip empty lines
            try:
                data.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"Error on line {i+1}")

df = pd.DataFrame(data)

# read appeals csv as DF

df_appeals = pd.read_csv(
    file_path2, 
    engine="c", 
    dtype=str, 
    quotechar='"', 
    on_bad_lines='skip',
    na_values=['', 'null']
)

# change column names to make merge easier 

df_appeals.columns = ['originating_court_information_id', 'date_created', 'date_modified', 'parent_docket_number',
       'assigned_to_str', 'ordering_judge_str', 'court_reporter',
       'date_disposed', 'date_filed', 'date_judgment', 'date_judgment_eod',
       'date_filed_noa', 'date_received_coa', 'assigned_to_id',
       'ordering_judge_id', 'docket_number_raw']

# keep for main df only columns we care about

main_df = df[["originating_court_information_id", "docket_number", "court_id", "cause", "nature_of_suit", "jurisdiction_type", "jury_demand", "date_last_index", "date_cert_granted", "date_cert_denied", "date_argued", "date_reargued", "date_reargument_denied", "date_filed", "date_terminated", "date_last_filing"]].copy()

# make jury_demand boolean
print(main_df["jury_demand"].unique())

main_df.loc[(main_df["jury_demand"]== "Yes") | (main_df["jury_demand"]== "Plaintiff")| (main_df["jury_demand"]== "Defendant")| (main_df["jury_demand"]== "Both"), "jury_demand"] = True
main_df.loc[main_df["jury_demand"]!= True,"jury_demand" ] = False

# add column for appeal filtering

main_df.insert(2, "is_appeal", False)
main_df.loc[main_df["originating_court_information_id"].notna(), "is_appeal"] = True


# check all is in order
print("IS APPEAL:", main_df["is_appeal"].unique())
print("JURY DEMAND:", main_df["jury_demand"].unique())

print(main_df.info())

# a few columns are empty both in the bulk data and in the updates
# we drop such columns

main_df.drop(columns=['date_last_index', 'date_cert_granted', 'date_cert_denied','date_reargued', 'date_reargument_denied'], inplace=True)


main_df["date_argued"] = pd.to_datetime(main_df["date_argued"], format= "%Y-%m-%d", errors="coerce")
main_df["date_filed"] = pd.to_datetime(main_df["date_filed"], format= "%Y-%m-%d", errors="coerce")
main_df["date_terminated"] = pd.to_datetime(main_df["date_terminated"], format= "%Y-%m-%d", errors="coerce")
main_df["date_last_filing"] = pd.to_datetime(main_df["date_last_filing"], format= "%Y-%m-%d", errors="coerce")
print(main_df.info())


# process appeals, whereby each appeal is identified by its docket number

df_appeals =pd.merge(main_df[["docket_number", "originating_court_information_id"]], df_appeals, on = "originating_court_information_id", how="inner")
df_appeals.drop(columns=['originating_court_information_id', 'date_created','date_modified', "court_reporter", 'assigned_to_id', 'ordering_judge_id','docket_number_raw', "assigned_to_str", "ordering_judge_str"], inplace=True)

# remove now useless column

main_df.drop(columns=["originating_court_information_id"], inplace=True)


# treat dates as datetime

print(df_appeals.info())

df_appeals["date_disposed"] = pd.to_datetime(df_appeals["date_disposed"], format= "%Y-%m-%d")
df_appeals["date_filed"] = pd.to_datetime(df_appeals["date_filed"], format= "%Y-%m-%d")
df_appeals["date_judgment"] = pd.to_datetime(df_appeals["date_judgment"], format= "%Y-%m-%d")
df_appeals["date_judgment_eod"] = pd.to_datetime(df_appeals["date_judgment_eod"], format= "%Y-%m-%d")
df_appeals["date_filed_noa"] = pd.to_datetime(df_appeals["date_filed_noa"], format= "%Y-%m-%d")
df_appeals["date_received_coa"] = pd.to_datetime(df_appeals["date_received_coa"], format= "%Y-%m-%d")


print(df_appeals.info())


print("MAIN DF", main_df.head())
print("APPEALS DF", df_appeals.head())

# save as parquet for storage


main_df.to_json(base_path /".."/"gold"/ "gold_database_dockets.parquet", engine="pyarrow")
df_appeals.to_json(base_path /".."/"gold"/ "gold_database_appeals.parquet", engine="pyarrow")

