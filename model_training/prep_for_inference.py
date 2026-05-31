import duckdb
from pathlib import Path
def prep_for_inference(docket_file, court_file):
    PROJECT_ROOT = Path(__file__).resolve().parent
    # File path for court metadata
    file_courts = PROJECT_ROOT / "silver"/ "courts"/ "courts_classified.parquet"

    # Initialize an in-memory DuckDB connection
    con = duckdb.connect()

    # Query to select only the explicit keys needed for your inference dictionary
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
        FROM '{docket_file}' d
        LEFT JOIN '{court_file}' c 
            ON d.court_id = c.court_id
    """

    try:
        # Execute query and convert the result directly into a Pandas DataFrame
        df = con.execute(query).df()
        
        # Convert the DataFrame rows into a list of dictionaries
        sample_case_list = df.to_dict(orient='records')
        return sample_case_list

    except Exception as e:
        print(f"Error during DuckDB query execution: {e}")
        return []
        
    finally:
        con.close()