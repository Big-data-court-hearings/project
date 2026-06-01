"""
Gold analytical case metrics table & longitudinal aggregations.

Produces:
- case_metrics.parquet          enriched case-level table
- active_cases_by_year.parquet
- active_cases_by_quarter.parquet
"""

import duckdb
from pathlib import Path
from _common import (
    SILVER_GLOB, GOLD_PATH, CASE_METRICS_CTE,
    connect, ensure, courts_file, START_YEAR,
)

output_file             = ensure(GOLD_PATH / "case_enhanced.parquet")
output_yearly_summary   = ensure(GOLD_PATH / "active_cases_by_year.parquet")
output_quarterly_summary= ensure(GOLD_PATH / "active_cases_by_quarter.parquet")

cf = courts_file()

print("Building main case metrics dataset...")

con = connect()

query = f"""
COPY (
    {CASE_METRICS_CTE.format(
        extra_cols=", activity_years, activity_quarters",
        source=f"read_parquet('{SILVER_GLOB}', union_by_name=True)",
        dedup_partition="court_id, docket_number",
    )}
    SELECT
        r.id, r.court_id, r.case_name, r.date_filed, r.date_terminated, r.date_last_filing,
        r.nature_of_suit, r.cause, r.blocked, r.source, r.is_appeal, r.date_modified,
        r.quarter_filed, r.quarter_terminated, r.docket_number, r.jury_demand,
        r.is_active, r.duration_days,
        r.year_filed, r.year_terminated,
        r.year_quarter_filed, r.year_quarter_terminated,
        r.activity_years, r.activity_quarters,
        c.circuit, c.level, c.is_federal, c.jurisdiction
    FROM ranked r
    LEFT JOIN read_parquet('{cf.as_posix()}') c ON r.court_id = c.court_id
    WHERE r.row_num = 1
      AND r.id IS NOT NULL
      AND r.date_filed IS NOT NULL
      AND r.docket_number IS NOT NULL AND r.docket_number != ''
      AND (r.is_active = TRUE OR r.year_terminated > {START_YEAR})
) TO '{output_file.as_posix()}' (FORMAT 'PARQUET', CODEC 'SNAPPY');
"""

con.execute(query)
print(f"Case metrics saved to: {output_file}")


# Unnest longitudinal aggregations directly from the parquet we just wrote — no re-scan of silver
src = output_file.as_posix()

for label, col, out in [
    ("yearly",    "activity_years",    output_yearly_summary),
    ("quarterly", "activity_quarters", output_quarterly_summary),
]:
    print(f"Generating {label} active volumes by court...")
    con.execute(f"""
    COPY (
        WITH unnested AS (
            SELECT court_id, circuit, unnest({col}) AS active_period
            FROM read_parquet('{src}')
        )
        SELECT court_id, circuit, active_period, COUNT(*) AS active_cases_count
        FROM unnested
        GROUP BY court_id, circuit, active_period
        ORDER BY court_id, active_period
    ) TO '{out.as_posix()}' (FORMAT 'PARQUET', CODEC 'SNAPPY');
    """)
    print(f"Saved: {out}")
