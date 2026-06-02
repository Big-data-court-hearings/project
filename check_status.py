import duckdb
import sys
from pathlib import Path

# Setup paths
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.append(str(PROJECT_ROOT))
from ingestion.config import SILVER_PATH

silver_files = (Path(SILVER_PATH) / "*.parquet").as_posix()

# ============================================================
# INPUT 
# ============================================================
TARGET_COURT = input("Please, enter a court_id (es. 'ganb'): ").lower()
TARGET_DOCKET = input("Please, enter a docket_number (es. '26-57212'): ")

# ============================================================
# CONNECT & QUERY
# ============================================================
print(f"Currently searching for {TARGET_DOCKET} in the court {TARGET_COURT}...")

con = duckdb.connect()

query = f"""
SELECT 
    case_name, 
    date_terminated,
    date_filed,
FROM read_parquet('{silver_files}')
WHERE docket_number = ? 
  AND court_id = ?
"""

docket_df = con.execute(query, [TARGET_DOCKET, TARGET_COURT]).df()

# ============================================================
# OUTPUT 
# ============================================================
if docket_df.empty:
    print(f"Error: No case found with docket_number {TARGET_DOCKET} and court_id {TARGET_COURT}.")
else:
    row = docket_df.iloc[0]
    case_name = row["case_name"]
    termination = row["date_terminated"]
    date_filed = row["date_filed"]
    
    print(f"\n--- Record found ---\n")
    print(f"Case name: {case_name}, filed on {date_filed}")
    
    # Controllo stato chiusura
    if termination is None or str(termination).lower() == "nan" or str(termination).strip() == "":
        print("Status: The case is still open.")
    else:
        print(f"Status: Closed. Termination date: {termination}")