"""
Gold analytical case metrics for the database dockets file.

Produces:
- database_case_metrics.parquet 
"""

from pathlib import Path
from _common import SILVER_PATH, GOLD_PATH, connect, ensure

silver_file = (Path(SILVER_PATH) / "database_dockets_latest.parquet").as_posix()
output_file = ensure(GOLD_PATH / "database_case_metrics.parquet")

print("Building database case metrics dataset...")

con = connect()

# Optimized SQL query handling both closed and open cases
query = f"""
SELECT 
    id, court_id, case_name, date_filed, date_terminated, date_last_filing,
    blocked, is_appeal, date_modified,
    quarter_filed, quarter_terminated, docket_number, jury_demand,
    year_filed, year_terminated, "nature_of_suit", "cause",
    duration_days
FROM (
    SELECT 
        *,
        -- Safely extract calendar years by casting the string columns to DATE type
        YEAR(date_filed::DATE) AS year_filed,
        YEAR(date_terminated::DATE) AS year_terminated,
        
        -- Compute difference in days: if date_terminated is missing, calculate up to 2026-03-31
        DATE_DIFF('day', date_filed::DATE, COALESCE(date_terminated::DATE, '2026-03-31'::DATE)) AS duration_days,
        
        -- Keeps your simplified deduplication rule
        ROW_NUMBER() OVER (
            PARTITION BY docket_number, court_id
            ORDER BY date_modified DESC
        ) AS row_num
    FROM read_parquet('{silver_file}')
    WHERE date_filed IS NOT NULL
      -- FILTRO DI SANITÀ DEI DATI: La chiusura deve essere successiva o uguale all'apertura
      AND (date_terminated IS NULL OR date_filed::DATE <= date_terminated::DATE)
) ranked
WHERE row_num = 1
"""

df = con.execute(query).df()
df.to_parquet(output_file, index=False)

print(f"Output: {output_file}")
print(df.info())
print(df.head())
print("N. records: ", len(df))