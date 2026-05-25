from pathlib import Path
import duckdb

BASE_DIR = Path(__file__).resolve().parent.parent

GOLD_DIR = BASE_DIR / "gold"

con = duckdb.connect()

query = f"""
SELECT
    court_id,
    active_cases,
    resolved_cases,
    mean_duration
FROM read_parquet('{GOLD_DIR}/court_performance_metrics.parquet')
ORDER BY active_cases DESC
LIMIT 20
"""

df = con.execute(query).df()

print(df)