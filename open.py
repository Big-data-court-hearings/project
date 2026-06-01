import pandas as pd

# 1. Load cache
df = pd.read_parquet("gold/metrics/backlog_evolution_by_quarter.parquet")

print(df.head())

df2 = pd.read_parquet("gold/metrics/case_enhanced.parquet")
print(df2.columns)

