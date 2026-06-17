import duckdb
from pathlib import Path

base_path    = Path(__file__).parent
CATALOG_PATH = (base_path / ".." / "silver_catalog.ducklake").resolve()
DATA_PATH    = (base_path / ".." / "silver" / "data").resolve()
EXISTING_PARQUET = (base_path / ".." / "silver" / "database_dockets_latest.parquet").resolve()

# print(f"Catalog : {CATALOG_PATH} (exists: {CATALOG_PATH.exists()})")
# print(f"Data    : {DATA_PATH} (exists: {DATA_PATH.exists()})")
# print(f"Parquet : {EXISTING_PARQUET} (exists: {EXISTING_PARQUET.exists()})")

DATA_PATH.mkdir(parents=True, exist_ok=True)

con = duckdb.connect()
con.execute(
    f"ATTACH 'ducklake:{CATALOG_PATH.as_posix()}' AS silver "
    f"(DATA_PATH '{DATA_PATH.as_posix()}', OVERRIDE_DATA_PATH TRUE)"
)

print("Attached. Creating table...")
con.execute(f"""
    CREATE TABLE silver.dockets AS
    SELECT * REPLACE (CAST(docket_number AS VARCHAR) AS docket_number)
    FROM read_parquet('{EXISTING_PARQUET.as_posix()}')
""")

print("Table created. Verifying...")
count = con.execute("SELECT COUNT(*) FROM silver.dockets").fetchone()[0]
print(f"Rows in silver.dockets: {count}")

con.close()
print("Migration done.")