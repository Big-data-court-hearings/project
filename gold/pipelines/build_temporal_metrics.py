"""
Temporal analytics metrics pipeline.

Produces inflow and outflow aggregations for circuits:
- case_inflow_by_year.parquet  / case_outflow_by_year.parquet
- case_inflow_by_quarter.parquet / case_outflow_by_quarter.parquet  
"""

from _common import GOLD_PATH, connect_gold, ensure, START_YEAR


paths = {
    "inflow_year":     ensure(GOLD_PATH / "case_inflow_by_year.parquet"),
    "outflow_year":    ensure(GOLD_PATH / "case_outflow_by_year.parquet"),
    "inflow_quarter":  ensure(GOLD_PATH / "case_inflow_by_quarter.parquet"),
    "outflow_quarter": ensure(GOLD_PATH / "case_outflow_by_quarter.parquet"),
}

print("Connecting to DuckDB...")
con = connect_gold(read_only=True)
# --- Yearly ---

print("Building yearly inflow...")
inflow_year = con.execute(f"""
SELECT year_filed, COUNT(*) AS filed_cases
FROM gold.case_metrics
WHERE year_filed > {START_YEAR} AND year_terminated > {START_YEAR}
GROUP BY year_filed
ORDER BY year_filed
""").df()
inflow_year.to_parquet(paths["inflow_year"], index=False)

print("Building yearly outflow...")
outflow_year = con.execute(f"""
SELECT year_terminated, COUNT(*) AS terminated_cases
FROM gold.case_metrics
WHERE year_terminated IS NOT NULL
  AND year_terminated > {START_YEAR}
  AND year_filed > {START_YEAR}
GROUP BY year_terminated
ORDER BY year_terminated
""").df()
outflow_year.to_parquet(paths["outflow_year"], index=False)

# --- Quarterly (by circuit) ---

print("Building quarterly inflow by circuit...")
inflow_quarter = con.execute(f"""
SELECT
    year_quarter_filed,
    circuit,
    COUNT(*) AS inflow,
    AVG(duration_days) AS avg_resolution_days,
    SUM(CASE WHEN is_active THEN 1 ELSE 0 END) AS active_cases
FROM gold.case_metrics
WHERE year_quarter_filed IS NOT NULL AND year_filed > {START_YEAR}
GROUP BY year_quarter_filed, circuit
ORDER BY year_quarter_filed, circuit
""").df()
inflow_quarter.to_parquet(paths["inflow_quarter"], index=False)

print("Building quarterly outflow by circuit...")
outflow_quarter = con.execute(f"""
SELECT
    year_quarter_terminated,
    circuit,
    COUNT(*) AS outflow,
    AVG(duration_days) AS avg_resolution_days,
FROM gold.case_metrics
WHERE year_quarter_terminated IS NOT NULL AND year_terminated > {START_YEAR}
GROUP BY year_quarter_terminated, circuit
ORDER BY year_quarter_terminated, circuit
""").df()
outflow_quarter.to_parquet(paths["outflow_quarter"], index=False)

print("\n=== YEARLY INFLOW ===");  print(inflow_year)
print("\n=== YEARLY OUTFLOW ==="); print(outflow_year)
print("\n=== QUARTERLY INFLOW ===");  print(inflow_quarter.head())
print("\n=== QUARTERLY OUTFLOW ==="); print(outflow_quarter.head())
