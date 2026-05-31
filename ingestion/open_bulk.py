"""This script filters through the massive Courtlistener dataset to retrieve only cases terminated from 2023 onwards"""

from pathlib import Path
import duckdb

base_path = Path(__file__).parent 

# Configure your input and output file paths
input_file = base_path / ".."/"dockets-2026-03-31.csv"
output_file = base_path / ".."/"data" / "dockets_terminated_23_onwards.jsonl"

# Ensure output directory exists
output_file.parent.mkdir(parents=True, exist_ok=True)

print(f"Connecting to DuckDB and filtering records from: {input_file.name}...")

con = duckdb.connect()

# Vectorized pipeline: Forces problematic column to VARCHAR and filters efficiently
query = f"""
COPY (
    SELECT *
    FROM read_csv_auto(
        '{input_file.as_posix()}',
        types={{'pacer_case_id': 'VARCHAR'}}
    )
    WHERE 
        date_terminated IS NOT NULL
        -- Highly efficient vectorized boundary check
        AND date_terminated >= '2023-01-01'
) TO '{output_file.as_posix()}' (FORMAT 'JSON', ARRAY FALSE);
"""

try:
    con.execute(query)
    
    # Quick row count validation summary
    total_rows = con.execute(f"SELECT COUNT(*) FROM read_json_auto('{output_file.as_posix()}')").fetchone()[0]
    print(f"Success! Saved {total_rows} matching records to {output_file.name}")

except Exception as e:
    print(f"An error occurred during processing: {e}")