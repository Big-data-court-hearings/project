"""
Gold analytical case metrics for the database dockets file.

Produces:
- database_case_metrics.parquet  (no court join, no cohort filter, no arrays)
"""

from pathlib import Path
from _common import SILVER_PATH, GOLD_PATH, CASE_METRICS_CTE, connect, ensure

silver_file = (Path(SILVER_PATH) / "database_dockets_latest.parquet").as_posix()
output_file = ensure(GOLD_PATH / "database_case_metrics.parquet")

print("Building database case metrics dataset...")

con = connect()

query = f"""
{CASE_METRICS_CTE.format(
    extra_cols="",
    source=f"read_parquet('{silver_file}')",
    dedup_partition="docket_number",
)}
SELECT
    id, court_id, case_name, date_filed, date_terminated, date_last_filing,
    nature_of_suit, cause, blocked, source, is_appeal, date_modified,
    quarter_filed, quarter_terminated, docket_number, jury_demand,
    is_active, duration_days,
    year_filed, year_terminated,
    year_quarter_filed, year_quarter_terminated
FROM ranked
WHERE row_num = 1
"""

df = con.execute(query).df()
df.to_parquet(output_file, index=False)

print(f"Output: {output_file}")
print(df.info())
print(df.head())
