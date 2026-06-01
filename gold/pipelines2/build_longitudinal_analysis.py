"""
Longitudinal active volume metrics engine.

Produces (by court and by circuit, yearly and quarterly):
- metrics/active_cases_by_year.parquet
- metrics/active_cases_by_quarter.parquet
- metrics/active_cases_by_circuit_year.parquet
- metrics/active_cases_by_circuit_quarter.parquet
"""

from pathlib import Path
from _common import GOLD_PATH, connect, ensure

case_metrics_file = GOLD_PATH / "case_enhanced.parquet"

if not case_metrics_file.exists():
    raise FileNotFoundError(f"Missing: {case_metrics_file}. Run build_case_metrics.py first.")

outputs = {
    "court_year":     ensure(GOLD_PATH /"active_cases_by_year.parquet"),
    "court_quarter":  ensure(GOLD_PATH / "active_cases_by_quarter.parquet"),
    "circuit_year":   ensure(GOLD_PATH / "active_cases_by_circuit_year.parquet"),
    "circuit_quarter":ensure(GOLD_PATH / "active_cases_by_circuit_quarter.parquet"),
}

src = case_metrics_file.as_posix()

print("Connecting to DuckDB...")
con = connect()

aggregations = [
    ("court_year",     "court_id, circuit,", "activity_years",    "active_year",    "court_id, active_year"),
    ("court_quarter",  "court_id, circuit,", "activity_quarters", "active_quarter", "court_id, active_quarter"),
    ("circuit_year",   "",                   "activity_years",    "active_year",    "circuit, active_year"),
    ("circuit_quarter","",                   "activity_quarters", "active_quarter", "circuit, active_quarter"),
]

for key, extra_select, arr_col, alias, order_by in aggregations:
    circuit_filter = "WHERE circuit IS NOT NULL" if not extra_select else ""
    select_cols = f"{extra_select} circuit," if extra_select else "circuit,"
    print(f"Processing {key}...")
    con.execute(f"""
    COPY (
        WITH unnested_data AS (
            SELECT {select_cols} UNNEST({arr_col}) AS {alias}
            FROM read_parquet('{src}')
            {circuit_filter}
        )
        SELECT {select_cols} {alias}, COUNT(*) AS active_cases_count
        FROM unnested_data
        GROUP BY {select_cols} {alias}
        ORDER BY {order_by}
    ) TO '{outputs[key].as_posix()}' (FORMAT 'PARQUET', CODEC 'SNAPPY');
    """)
    print(f"Saved: {outputs[key]}")

print("\n=== PREVIEW: circuit quarterly ===")
print(con.execute(f"SELECT * FROM read_parquet('{outputs['circuit_quarter'].as_posix()}') LIMIT 5").df().to_string(index=False))

print("\n=== PREVIEW: court quarterly ===")
print(con.execute(f"SELECT * FROM read_parquet('{outputs['court_quarter'].as_posix()}') LIMIT 5").df().to_string(index=False))
