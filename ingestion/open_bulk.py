"""This script filters through the massive Courtlistener dataset to retrieve 
cases terminated from 2023 onwards AND active cases filed from 2020 onwards (6-year limit).
"""

from pathlib import Path
import duckdb

base_path = Path(__file__).parent.parent

# Configure your input and output file paths
input_file = base_path  / "dockets-2026-03-31.csv"
output_file = base_path / "data" / "dockets_observatory_2020_onwards.jsonl"

# Ensure output directory exists
output_file.parent.mkdir(parents=True, exist_ok=True)

print(f"Connecting to DuckDB and filtering records from: {input_file.name}...")

con = duckdb.connect()

# Vectorized pipeline with an optimized lookback boundary for active cases
query = f"""
COPY (
    SELECT *
    FROM read_csv_auto(
        '{input_file.as_posix()}',
        types={{'pacer_case_id': 'VARCHAR'}}
    )
    WHERE 
        -- Condition 1: Cases terminated from 2023 onwards
        (date_terminated IS NOT NULL AND date_terminated >= '2023-01-01')
        
        OR 
        
        -- Condition 2: Active cases filed within the last 6 years (2020+)
        (date_terminated IS NULL AND date_filed >= '2020-01-01')
) TO '{output_file.as_posix()}' (FORMAT 'JSON', ARRAY FALSE);
"""

try:
    con.execute(query)
    
    # Quick row count validation summary
    total_rows = con.execute(f"SELECT COUNT(*) FROM read_json_auto('{output_file.as_posix()}')").fetchone()[0]
    print(f"Success! Saved {total_rows} matching records to {output_file.name}")

except Exception as e:
    print(f"An error occurred during processing: {e}")