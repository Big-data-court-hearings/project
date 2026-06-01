import pandas as pd
import json

batches = ["batch1", "batch2", "batch3", "batch4"]
for batch in batches:
    with open(f"{batch}.json") as f:
        file = json.load(f)
    to_add = file["courts"]
    if batch == "batch1":
        df = pd.DataFrame(to_add)
        print(len(to_add))
    else:
        batch1 = pd.DataFrame(to_add)
        df = pd.concat([df, batch1])

print(len(df))
print(df.head())

other_df = pd.read_parquet("silver/courts/courts_classified.parquet")
df = pd.concat([df, other_df])
print(df.head())
df = df.drop(columns=["district_id", "district_name"])
print((df["level"].unique()))
df.to_parquet("silver/courts/courts_classified.parquet")