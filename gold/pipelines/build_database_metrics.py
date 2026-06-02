"""
Gold analytical case metrics for the database dockets file.

Produces:
- database_case_metrics.parquet  (no court join, no cohort filter, no arrays)
"""

from pathlib import Path
from _common import SILVER_PATH, GOLD_PATH, connect, ensure

silver_file = (Path(SILVER_PATH) / "database_dockets_latest.parquet").as_posix()
output_file = ensure(GOLD_PATH / "database_case_metrics.parquet")

print("Building database case metrics dataset...")

con = connect()

# Pure SQL query keeping your clean structure, optimized strictly for CLOSED cases with duration
query = f"""
SELECT 
    id, court_id, case_name, date_filed, date_terminated, date_last_filing,
    nature_of_suit, cause, blocked, source, is_appeal, date_modified,
    quarter_filed, quarter_terminated, docket_number, jury_demand,
    year_filed, year_terminated,
    duration_days,
FROM (
    SELECT 
        *,
        -- Safely extract calendar years by casting the string columns to DATE type
        YEAR(date_filed::DATE) AS year_filed,
        YEAR(date_terminated::DATE) AS year_terminated,
        
        -- Compute the difference in days between filing and termination
        DATE_DIFF('day', date_filed::DATE, date_terminated::DATE) AS duration_days,
        
        -- Keeps your simplified deduplication rule
        ROW_NUMBER() OVER (
            PARTITION BY docket_number, court_id
            ORDER BY date_modified DESC
        ) AS row_num
    FROM read_parquet('{silver_file}')
) ranked
WHERE row_num = 1
  -- Filters strictly for closed cases and ensures a logical chronological timeline
  AND date_terminated IS NOT NULL 
  AND date_filed::DATE <= date_terminated::DATE
"""

df = con.execute(query).df()
df.to_parquet(output_file, index=False)

print(f"Output: {output_file}")
print(df.info())
print(df.head())