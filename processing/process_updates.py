import json
import pandas as pd
from pathlib import Path
import csv 
import numpy as np

base_path = Path(__file__).parent 

file_path = base_path /".."/"data"/ "raw_json"/"latest_docket_update.jsonl"

# load jsonl into DF

data = []

# load jsonl as list

with open(file_path, 'r', encoding='utf-8') as f:
    for i, line in enumerate(f):
        if line.strip(): 
            try:
                data.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"Error on line {i+1}")

data_main = []
data_appeals = []

# separate appeals extra info from normal docket

for line in data:
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

df_main = pd.DataFrame(data_main)
print(df_main.head())
df_appeals = pd.DataFrame(data_appeals)
print(df_appeals.head())

# clean df_main

print(df_main.columns)

df_main = df_main.drop(columns=['resource_uri', 'id', 'court','idb_data', 'clusters',
       'audio_files', 'assigned_to', 'referred_to', 'bankruptcy_information',
       'absolute_url', 'date_created', 'date_modified', 'source',
       'appeal_from_str', 'assigned_to_str', 'referred_to_str', 'panel_str','case_name_short', 'case_name',
       'case_name_full', 'slug', 'docket_number_core',
       'docket_number_raw', 'docket_number_source', 'federal_dn_office_code',
       'federal_dn_case_type', 'federal_dn_judge_initials_assigned',
       'federal_dn_judge_initials_referred', 'federal_defendant_number',
       'pacer_case_id','appellate_fee_status',
       'appellate_case_type_information', 'mdl_status', 'filepath_ia',
       'filepath_ia_json', 'ia_upload_failure_count', 'ia_needs_upload',
       'ia_date_first_change', 'date_blocked', 'blocked', 'appeal_from',
       'parent_docket', 'tags', 'panel'])

df_main["jury_demand"][(df_main["jury_demand"] == "Plaintiff") | (df_main["jury_demand"] == "Defendant")] = True
df_main["jury_demand"][df_main["jury_demand"] != True] = False

df_main = df_main.fillna(value=np.nan)
df_main = df_main.replace([""], np.nan)
print(df_main.head())

print(df_main.info())

df_main["date_argued"] = pd.to_datetime(df_main["date_argued"], format= "%Y-%m-%d")
df_main["date_filed"] = pd.to_datetime(df_main["date_filed"], format= "%Y-%m-%d")
df_main["date_terminated"] = pd.to_datetime(df_main["date_terminated"], format= "%Y-%m-%d")
df_main["date_last_filing"] = pd.to_datetime(df_main["date_last_filing"], format= "%Y-%m-%d")

# a few columns are empty both in the bulk data and in the updates
# we drop such columns

df_main.drop(columns=['date_last_index', 'date_cert_granted', 'date_cert_denied','date_reargued', 'date_reargument_denied'], inplace=True)

print(df_main.info())

# clean df_appeals

print(df_appeals.columns)
df_appeals = df_appeals.drop(columns=['resource_uri', 'id', 'date_created', 'date_modified',
       'docket_number_raw', 'assigned_to_str', 'ordering_judge_str',
       'court_reporter', 'assigned_to', 'ordering_judge'])
df_appeals = df_appeals.fillna(value=np.nan)
df_appeals = df_appeals.replace([""], np.nan)

print(df_appeals.info())
df_appeals["date_disposed"] = pd.to_datetime(df_appeals["date_disposed"], format= "%Y-%m-%d")
df_appeals["date_filed"] = pd.to_datetime(df_appeals["date_filed"], format= "%Y-%m-%d")
df_appeals["date_judgment"] = pd.to_datetime(df_appeals["date_judgment"], format= "%Y-%m-%d")
df_appeals["date_judgment_eod"] = pd.to_datetime(df_appeals["date_judgment_eod"], format= "%Y-%m-%d")
df_appeals["date_filed_noa"] = pd.to_datetime(df_appeals["date_filed_noa"], format= "%Y-%m-%d")
df_appeals["date_received_coa"] = pd.to_datetime(df_appeals["date_received_coa"], format= "%Y-%m-%d")
df_appeals.drop(columns=["date_rehearing_denied"], inplace=True)
print(df_appeals.info())


# save as parquet for storage

df_main.to_parquet(base_path /".."/"bronze"/"bronze_update_dockets11-05.parquet", engine = "pyarrow")
df_appeals.to_parquet(base_path /".."/"bronze"/"bronze_update_appeals11-05.parquet", engine = "pyarrow")


