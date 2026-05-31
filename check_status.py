import duckdb
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.append(str(PROJECT_ROOT))

from ingestion.config import (
    SILVER_PATH
    )

# ============================================================
# PATHS & CONFIGURATION
# ============================================================

silver_files = (Path(SILVER_PATH) / "*.parquet").as_posix()

# target docket number to search for
answered = False
while answered == False:
    answer = input("Do you want to query a specific docket number or use a default value? (specific/default)\n")
    if answer.lower() == "specific":
        TARGET_DOCKET = input("Please, write the docket number\n")
        answered = True
    elif answer.lower() == "default":
        TARGET_DOCKET = "2:23-cv-01234"
        answered = True
    else:
        print("I didn't understand. Please, answer again")

# ============================================================
# CONNECT TO DUCKDB
# ============================================================

print("Connecting to DuckDB...")

con = duckdb.connect()

# ============================================================
# QUERY SPECIFIC DOCKET
# ============================================================

print(f"Searching for docket number: {TARGET_DOCKET}...")

# parameterized query to prevent execution syntax errors
query = f"""
SELECT *
FROM read_parquet('{silver_files}')
WHERE docket_number = ?
"""

docket_df = con.execute(
    query, 
    [TARGET_DOCKET]
).df()

# ============================================================
# FINAL OUTPUT
# ============================================================

if len(docket_df) == 0:
    print(f"\nNo record found for docket: {TARGET_DOCKET}")
else:
    termination = docket_df["date_terminated"].tolist()[0]
    if termination == None or termination == "NaN":
        print(f"\nRecord found. The case hasn't been closed yet.")
    else:
        print(f"The case terminated on the date: {termination}")
