import duckdb
from pathlib import Path

def prep_for_inference(docket_file, court_file, court_stats_file):
    con = duckdb.connect()

    query = f"""
        SELECT
            d.court_id,
            d.blocked,
            d.is_appeal,
            d.jury_demand,
            d.quarter_filed,
            YEAR(TRY_CAST(d.date_filed AS TIMESTAMP)) AS year_filed,
            c.circuit,
            c.level,
            c.is_federal,
            c.jurisdiction,
            cs.court_censoring_rate,
            cs.court_case_volume
        FROM '{docket_file}' d
        LEFT JOIN '{court_file}' c
            ON d.court_id = c.court_id
        LEFT JOIN '{court_stats_file}' cs
            ON d.court_id = cs.court_id
    """

    try:
        df = con.execute(query).df()
        return df.to_dict(orient="records")

    except Exception as e:
        print(f"Error during DuckDB query execution: {e}")
        return []

    finally:
        con.close()
