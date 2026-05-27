from pathlib import Path
import os
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BRONZE = PROJECT_ROOT / 'bronze' / 'dockets' / 'dockets_raw.jsonl'
SILVER = PROJECT_ROOT / 'silver' / 'dockets_clean.parquet'
CASE_METRICS = PROJECT_ROOT / 'gold' / 'metrics' / 'case_metrics.parquet'
HIST_LOG = PROJECT_ROOT / 'logs' / 'historical_ingestion.csv'
ING_LOG = PROJECT_ROOT / 'logs' / 'ingestion_history.csv'

summary = {}

# Bronze size and total records
if BRONZE.exists():
    summary['bronze_bytes'] = BRONZE.stat().st_size
    # count lines
    with open(BRONZE, 'r', encoding='utf-8') as fh:
        lines = sum(1 for _ in fh)
    summary['bronze_records'] = lines
else:
    summary['bronze_bytes'] = 0
    summary['bronze_records'] = 0

# Silver / case metrics
if SILVER.exists():
    df_silver = pd.read_parquet(SILVER)
    summary['silver_records'] = len(df_silver)
else:
    summary['silver_records'] = None

if CASE_METRICS.exists():
    df_case = pd.read_parquet(CASE_METRICS)
    summary['total_cases'] = len(df_case)
    if 'is_active' in df_case.columns:
        summary['active_cases'] = int(df_case['is_active'].sum())
        summary['resolved_cases'] = int((~df_case['is_active']).sum())
    else:
        summary['active_cases'] = None
        summary['resolved_cases'] = None

    # yearly coverage
    yf = df_case['year_filed'].dropna().astype(int)
    yt = df_case['year_terminated'].dropna().astype(int)
    summary['year_filed_min'] = int(yf.min()) if not yf.empty else None
    summary['year_filed_max'] = int(yf.max()) if not yf.empty else None
    summary['year_terminated_min'] = int(yt.min()) if not yt.empty else None
    summary['year_terminated_max'] = int(yt.max()) if not yt.empty else None

else:
    summary['total_cases'] = None

# ingestion runtimes
hist_runtime = 0.0
hist_rows = 0
if HIST_LOG.exists():
    try:
        hist = pd.read_csv(HIST_LOG)
        if 'runtime_seconds' in hist.columns:
            hist_runtime = hist['runtime_seconds'].sum()
            hist_rows = len(hist)
    except Exception:
        pass

ing_runtime = 0.0
if ING_LOG.exists():
    try:
        ing = pd.read_csv(ING_LOG)
        if 'runtime_seconds' in ing.columns:
            ing_runtime = ing['runtime_seconds'].sum()
    except Exception:
        pass

summary['historical_runtime_seconds'] = hist_runtime
summary['historical_windows'] = hist_rows
summary['incremental_runtime_seconds'] = ing_runtime

# print summary
print('Ingestion Summary')
print('-----------------')
print(f"Bronze file: {BRONZE}")
print(f"Bronze bytes: {summary['bronze_bytes']:,}")
print(f"Bronze records: {summary['bronze_records']:,}")
print(f"Silver records: {summary.get('silver_records')}")
print(f"Total cases (Gold): {summary.get('total_cases')}")
print(f"Active cases: {summary.get('active_cases')}")
print(f"Resolved cases: {summary.get('resolved_cases')}")
print('Yearly coverage:')
print(f"  filed: {summary.get('year_filed_min')} -> {summary.get('year_filed_max')}")
print(f"  terminated: {summary.get('year_terminated_min')} -> {summary.get('year_terminated_max')}")
print(f"Historical windows processed: {summary['historical_windows']}")
print(f"Historical runtime (s): {summary['historical_runtime_seconds']}")
print(f"Incremental runtime (s): {summary['incremental_runtime_seconds']}")
