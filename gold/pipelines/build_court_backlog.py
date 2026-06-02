"""
Quarterly inflow, outflow, active cases, and clearance ratio by court_id.

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
    WITH baseline AS (
        SELECT court_id, COUNT(*) AS baseline_cases
        FROM read_parquet('{src}')
        WHERE year_filed < 2023 
          AND (year_terminated >= 2023 OR year_terminated IS NULL)
        GROUP BY court_id
    ),
    inflow AS (
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
    ),
    active_cases AS (
        SELECT court_id, year_quarter, COUNT(*) AS active_cases_count
        FROM (
            SELECT court_id, unnest(activity_quarters) AS year_quarter
            FROM read_parquet('{src}')
        )
        WHERE year_quarter IN ({quarters})
        GROUP BY court_id, year_quarter
    ),
    joined AS (
        SELECT
            COALESCE(i.court_id, o.court_id, a.court_id) AS court_id,
            COALESCE(i.year_quarter, o.year_quarter, a.year_quarter) AS year_quarter,
            COALESCE(i.filed_cases, 0) AS inflow_cases,
            COALESCE(o.terminated_cases, 0) AS outflow_cases,
            COALESCE(a.active_cases_count, 0) AS active_cases_count
        FROM inflow i
        FULL OUTER JOIN outflow o ON i.court_id = o.court_id AND i.year_quarter = o.year_quarter
        FULL OUTER JOIN active_cases a ON COALESCE(i.court_id, o.court_id) = a.court_id 
                                      AND COALESCE(i.year_quarter, o.year_quarter) = a.year_quarter
    )
    SELECT
        j.*,
        -- Backlog calculation
        COALESCE(b.baseline_cases, 0) + SUM(inflow_cases - outflow_cases) OVER (
            PARTITION BY j.court_id 
            ORDER BY j.year_quarter
        ) AS total_backlog,
        -- Quarterly Clearance Ratio (Flow efficiency)
        CASE 
            WHEN inflow_cases > 0 THEN ROUND(CAST(outflow_cases AS DOUBLE) / inflow_cases, 4)
            ELSE NULL 
        END AS backlog_clearance_ratio,
        -- Total Clearance Efficiency (Stock efficiency)
        CASE 
            WHEN (COALESCE(b.baseline_cases, 0) + SUM(inflow_cases - outflow_cases) OVER (PARTITION BY j.court_id ORDER BY j.year_quarter)) > 0
            THEN ROUND(CAST(outflow_cases AS DOUBLE) / (COALESCE(b.baseline_cases, 0) + SUM(inflow_cases - outflow_cases) OVER (PARTITION BY j.court_id ORDER BY j.year_quarter)), 4)
            ELSE NULL 
        END AS clearance_efficiency
    FROM joined j
    LEFT JOIN baseline b ON j.court_id = b.court_id
    ORDER BY court_id, year_quarter
) TO '{backlog_evolution_file.as_posix()}' (FORMAT 'PARQUET', CODEC 'SNAPPY');
""")
print(f"Exported: {backlog_evolution_file}")
preview = con.execute(f"SELECT * FROM read_parquet('{backlog_evolution_file.as_posix()}') LIMIT 20").df()
print(preview)