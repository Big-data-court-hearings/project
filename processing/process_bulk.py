"""This script processes raw dockets into a clean silver Parquet layer,
generating native list arrays tracking every year and quarter a case was active
between 2023 and 2026, completely filtering out any rows with chronological anomalies.
"""

from pathlib import Path
import duckdb

base_path = Path(__file__).parent 
file_path = base_path / ".." / "data" / "dockets_observatory_2020_onwards.jsonl"
output_parquet = base_path / ".." / "silver" / "database_dockets_latest.parquet"

# Ensure output directory exists
output_parquet.parent.mkdir(parents=True, exist_ok=True)

print("Connecting to DuckDB and processing raw dataset...")
con = duckdb.connect()

query = f"""
COPY (
    WITH raw_data AS (
        SELECT 
            id,
            court_id,
            case_name,
            CAST(date_filed AS DATE) AS d_filed,
            CAST(date_terminated AS DATE) AS d_term,
            CAST(date_last_filing AS DATE) AS date_last_filing,
            nature_of_suit,
            cause,
            jurisdiction_type,
            blocked,
            source,
            docket_number,
            TRY_CAST(date_modified AS TIMESTAMP) AS date_modified,
            
            CASE 
                WHEN originating_court_information_id IS NOT NULL 
                     AND originating_court_information_id NOT IN ('', 'None') 
                THEN TRUE ELSE FALSE 
            END AS is_appeal,
            
            CASE 
                WHEN jury_demand IN ('Plaintiff', 'Defendant') THEN TRUE ELSE FALSE 
            END AS jury_demand,

            ROW_NUMBER() OVER (
                PARTITION BY court_id, docket_number 
                ORDER BY TRY_CAST(date_modified AS TIMESTAMP) DESC, id DESC
            ) AS row_num
        FROM read_json(
            '{file_path.as_posix()}',
            format='newline_delimited',
            columns={{
                id: 'BIGINT', court_id: 'VARCHAR', case_name: 'VARCHAR',
                date_filed: 'VARCHAR', date_terminated: 'VARCHAR', date_last_filing: 'VARCHAR',
                nature_of_suit: 'VARCHAR', cause: 'VARCHAR', jurisdiction_type: 'VARCHAR',
                blocked: 'BOOLEAN', source: 'VARCHAR', docket_number: 'VARCHAR',
                date_modified: 'VARCHAR', originating_court_information_id: 'VARCHAR', jury_demand: 'VARCHAR'
            }}
        )
    ),
    bounded_cases AS (
        SELECT 
            *,
            -- Establish window boundaries for year generation (2023-2026)
            GREATEST(2023, date_part('year', d_filed)) AS start_yr,
            LEAST(2026, COALESCE(date_part('year', d_term), 2026)) AS end_yr,
            
            -- Establish window boundaries for quarter generation
            GREATEST(CAST('2023-01-01' AS DATE), d_filed) AS start_q_date,
            LEAST(CAST('2026-03-31' AS DATE), COALESCE(d_term, CAST('2026-03-31' AS DATE))) AS end_q_date
        FROM raw_data
        WHERE row_num = 1
          AND id IS NOT NULL AND d_filed IS NOT NULL AND date_modified IS NOT NULL
          AND court_id IS NOT NULL AND docket_number IS NOT NULL AND docket_number != ''
          AND (d_term IS NULL OR date_part('year', d_term) IN (2023, 2024, 2025, 2026))
          
          -- 🛠️ FIX: Drop all chronological anomalies entirely
          AND (d_term IS NULL OR d_filed <= d_term)
          AND (GREATEST(2023, date_part('year', d_filed)) <= LEAST(2026, COALESCE(date_part('year', d_term), 2026)))
    )
    SELECT 
        id, court_id, case_name,
        strftime(d_filed, '%Y-%m-%d') AS date_filed,
        strftime(d_term, '%Y-%m-%d') AS date_terminated,
        strftime(date_last_filing, '%Y-%m-%d') AS date_last_filing,
        nature_of_suit, cause, jurisdiction_type, blocked, source, docket_number, date_modified,
        is_appeal, jury_demand,
        'q' || date_part('quarter', d_term) AS quarter_terminated,
        'q' || date_part('quarter', d_filed) AS quarter_filed,
        
        -- Clean structural array generations without needing fallback switches
        (
            SELECT list(yr) 
            FROM generate_series(CAST(start_yr AS INT), CAST(end_yr AS INT)) AS t(yr)
        ) AS activity_years,

        (
            SELECT list(DISTINCT date_part('year', q_day) || '-q' || date_part('quarter', q_day))
            FROM generate_series(start_q_date, end_q_date, INTERVAL 1 MONTH) AS t(q_day)
        ) AS activity_quarters

    FROM bounded_cases
) TO '{output_parquet.as_posix()}' (FORMAT 'PARQUET', CODEC 'SNAPPY');
"""

try:
    con.execute(query)

    # ============================================================
    # PERFORMANCE METRICS PREVIEW
    # ============================================================
    metrics = con.execute(f"""
        SELECT 
            MIN(date_filed) AS earliest, 
            MAX(date_filed) AS latest,
            COUNT(*) AS total_rows 
        FROM read_parquet('{output_parquet.as_posix()}')
    """).fetchone()

    print(f"\nEARLIEST CASE FILE DATE: {metrics[0]}")
    print(f"LATEST CASE FILE DATE: {metrics[1]}")
    print(f"Total processed clean records: {metrics[2]}")
    print(f"Silver layer parquet generated successfully via DuckDB.")

except Exception as e:
    print(f"An error occurred during execution: {e}")