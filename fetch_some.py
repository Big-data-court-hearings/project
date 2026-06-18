import duckdb
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
GOLD_CAT_PATH = (BASE_DIR / "gold_catalog.ducklake").resolve()
GOLD_DAT_PATH = (BASE_DIR / "gold" / "data").resolve()

con = duckdb.connect()
con.execute("INSTALL ducklake; LOAD ducklake;")
con.execute(
    f"ATTACH 'ducklake:{GOLD_CAT_PATH.as_posix()}' AS gold "
    f"(DATA_PATH '{GOLD_DAT_PATH.as_posix()}', OVERRIDE_DATA_PATH TRUE)"
)

# Define your N number of cases
N = 5  

# Query using UNION ALL and ORDER BY RANDOM()

query = """
    (
        SELECT id, court_id, docket_number, case_name, is_active
        FROM gold.main.case_metrics
        WHERE is_active = TRUE
          AND court_id IS NOT NULL
          AND docket_number IS NOT NULL
        ORDER BY RANDOM()
        LIMIT ?
    )
    UNION ALL
    (
        SELECT id, court_id, docket_number, case_name, is_active
        FROM gold.main.case_metrics
        WHERE is_active = FALSE
          AND court_id IS NOT NULL
          AND docket_number IS NOT NULL
        ORDER BY RANDOM()
        LIMIT ?
    )
"""

# Pass N twice—once for the open cases limit, once for the closed cases limit
rows = con.execute(query, [N, N]).fetchall()

# Print the mixed results
print("STILL OPEN CASES")
for row in rows[:N]:
    print(row)
print("CLOSED CASES")
for row in rows[N:]:
    print(row)

con.close()