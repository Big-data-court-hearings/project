"""this script processed the dockets terminated from 2023 until 
the 31st of March 2026. They represent the database (used also for training)"""

from pathlib import Path
import duckdb

base_path = Path(__file__).parent 
file_path = base_path / ".." / "data" / "dockets_terminated_23_onwards.jsonl"
output_parquet = base_path / ".." / "silver" / "database_dockets_latest.parquet"

# Ensure output directory exists
output_parquet.parent.mkdir(parents=True, exist_ok=True)

print("Connecting to DuckDB and processing raw dataset...")
con = duckdb.connect()

# Single-pass end-to-end analytical query with inline window deduplication
query = f"""
COPY (
    WITH raw_data AS (
        SELECT 
            id,
            court_id,
            case_name,
            CAST(date_filed AS DATE) AS date_filed,
            CAST(date_terminated AS DATE) AS date_terminated,
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
                THEN TRUE 
                ELSE FALSE 
            END AS is_appeal,
            
            CASE 
                WHEN jury_demand IN ('Plaintiff', 'Defendant') THEN TRUE 
                ELSE FALSE 
            END AS jury_demand,

            -- ⚡ Deduplication Logic: Rank by docket_number prioritizing the latest date_modified
            ROW_NUMBER() OVER (
                PARTITION BY docket_number 
                ORDER BY TRY_CAST(date_modified AS TIMESTAMP) DESC, id DESC
            ) AS row_num

        FROM read_json_auto('{file_path.as_posix()}')
    )
    SELECT 
        id,
        court_id,
        case_name,
        
        -- 🏅 SET EXPLICIT ISO STRINGS FOR THE PARQUET CORES (YYYY-MM-DD)
        strftime(date_filed, '%Y-%m-%d') AS date_filed,
        strftime(date_terminated, '%Y-%m-%d') AS date_terminated,
        strftime(date_last_filing, '%Y-%m-%d') AS date_last_filing,
        
        nature_of_suit,
        cause,
        jurisdiction_type,
        blocked,
        source,
        docket_number,
        
        -- Standardize timestamp metadata tracking field to ISO string sequence
        strftime(date_modified, '%Y-%m-%d %H:%M:%S') AS date_modified,
        
        is_appeal,
        jury_demand,
        'q' || date_part('quarter', date_terminated) AS quarter_terminated,
        'q' || date_part('quarter', date_filed) AS quarter_filed
    FROM raw_data
    WHERE 
        row_num = 1 -- 🏅 Retains only the latest modified entry per unique docket number
        AND id IS NOT NULL 
        AND date_filed IS NOT NULL 
        AND date_terminated IS NOT NULL 
        AND date_modified IS NOT NULL
        AND docket_number IS NOT NULL AND docket_number != ''
        AND date_part('year', date_terminated) IN (2023, 2024, 2025, 2026)
) TO '{output_parquet.as_posix()}' (FORMAT 'PARQUET', CODEC 'SNAPPY');
"""

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

print(f"\nEARLIEST CASE: {metrics[0]}")
print(f"LATEST CASE: {metrics[1]}")
print(f"Total processed clean records: {metrics[2]}")
print(f"Silver layer parquet generated successfully via DuckDB.")