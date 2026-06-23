"""
Duration analytics metrics pipeline.

Produces case duration by quarter for circuits and courts:
- case_duration_distribution_circuit_by_quarter.parquet 
- case_duration_distribution_court_by_quarter.parquet
"""

import duckdb
from _common import GOLD_PATH, ensure, START_YEAR, connect_gold


outputs = {
    "circuit": ensure(GOLD_PATH / "case_duration_distribution_circuit_by_quarter.parquet"),
    "court":   ensure(GOLD_PATH / "case_duration_distribution_court_by_quarter.parquet"),
}

def compute_stats(con: duckdb.DuckDBPyConnection, group_col: str, output_path: str):
    """
    Uses DuckDB SQL to perform grouped aggregation and quantile calculations
    directly on the parquet file.
    """
    query = f"""
    COPY (
        SELECT 
            year_quarter_terminated,
            {group_col},
            COUNT(duration_days) AS resolved_cases,
            ROUND(AVG(duration_days), 2) AS mean_duration,
            ROUND(MEDIAN(duration_days), 2) AS median_duration,
            ROUND(STDDEV(duration_days), 2) AS std_duration,
            MIN(duration_days) AS min_duration,
            MAX(duration_days) AS max_duration,
            ROUND(QUANTILE_CONT(duration_days, 0.75), 2) AS p75_duration,
            ROUND(QUANTILE_CONT(duration_days, 0.90), 2) AS p90_duration
        FROM gold.case_metrics
        WHERE duration_days IS NOT NULL 
          AND year_quarter_terminated IS NOT NULL
          AND duration_days >= 0
          AND CAST(SUBSTR(year_quarter_terminated, 1, 4) AS INTEGER) > {START_YEAR}
        GROUP BY year_quarter_terminated, {group_col}
        ORDER BY year_quarter_terminated, {group_col}
    ) TO '{output_path}' (FORMAT 'PARQUET', CODEC 'SNAPPY');
    """
    con.execute(query)

def main():
    con = connect_gold(read_only=True)
    
    tasks = [
        ("circuit", "circuit", outputs["circuit"]),
        ("court", "court_id", outputs["court"]),
    ]
    
    for label, group_col, out_path in tasks:
        print(f"Computing duration stats by {label}...")
        compute_stats(con, group_col, str(out_path))
        print(f"Exported: {out_path}")

if __name__ == "__main__":
    main()