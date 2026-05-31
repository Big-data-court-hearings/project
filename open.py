import pandas as pd

df = pd.read_parquet("silver/courts/courts_classified.parquet")
print(df["level"].unique())