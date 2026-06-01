"""
Quarterly inflow, outflow, and clearance ratio by court_id.

Produces:
- court_backlog_evolution.parquet
"""

from _common import GOLD_PATH, connect, ensure, QUARTERS_IN_WINDOW

case_metrics_file    = GOLD_PATH / "case_enhanced.parquet"
backlog_evolution_file = ensure(GOLD_PATH / "court_backlog_evolution.parquet")

src = case_metrics_file.as_posix()
quarters = ", ".join(f"'{q}'" for q in QUARTERS_IN_WINDOW)

print("Building court quarterly backlog evolution metrics...")
con = connect()

con.execute(f"""
COPY (
    WITH inflow AS (
        SELECT court_id, year_quarter_filed AS year_quarter, COUNT(*) AS filed_cases
        FROM read_parquet('{src}')
        WHERE year_quarter_filed IN ({quarters})
        GROUP BY court_id, year_quarter_filed
    ),
    outflow AS (
        SELECT court_id, year_quarter_terminated AS year_quarter, COUNT(*) AS terminated_cases
        FROM read_parquet('{src}')
        WHERE year_quarter_terminated IN ({quarters})
        GROUP BY court_id, year_quarter_terminated
    )
    SELECT
        COALESCE(i.court_id, o.court_id) AS court_id,
        COALESCE(i.year_quarter, o.year_quarter) AS year_quarter,
        COALESCE(i.filed_cases, 0) AS inflow_cases,
        COALESCE(o.terminated_cases, 0) AS outflow_cases,
        CASE
            WHEN COALESCE(i.filed_cases, 0) > 0
            THEN ROUND(CAST(COALESCE(o.terminated_cases, 0) AS DOUBLE) / i.filed_cases, 4)
        END AS backlog_clearance_ratio
    FROM inflow i
    FULL OUTER JOIN outflow o ON i.court_id = o.court_id AND i.year_quarter = o.year_quarter
    ORDER BY court_id, year_quarter
) TO '{backlog_evolution_file.as_posix()}' (FORMAT 'PARQUET', CODEC 'SNAPPY');
""")

print(f"Exported: {backlog_evolution_file}")
preview = con.execute(f"SELECT * FROM read_parquet('{backlog_evolution_file.as_posix()}') LIMIT 20").df()
print(preview)
