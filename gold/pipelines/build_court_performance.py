"""
Court and circuit performance metrics.

Merges active-case counts with duration distribution data.

Produces:
- metrics/court_performance_metrics.parquet
- metrics/circuit_performance_metrics.parquet
"""

import pandas as pd
from pathlib import Path
from _common import GOLD_PATH, ensure



paths = {
    "active_courts":           GOLD_PATH / "active_cases_by_court.parquet",
    "active_circuit": GOLD_PATH / "metrics_by_circuit.parquet",
    "duration_court":   GOLD_PATH / "case_duration_distribution_court_by_quarter.parquet",
    "duration_circuit":          GOLD_PATH / "case_duration_distribution_circuit_by_quarter.parquet",
    "out_court":        ensure(GOLD_PATH / "court_performance_metrics.parquet"),
    "out_circuit":      ensure(GOLD_PATH / "circuit_performance_metrics.parquet"),
}

DURATION_COLS = ["mean_duration", "median_duration", "std_duration", "min_duration", "max_duration", "p75_duration", "p90_duration"]
DESIRED_ORDER  = ["active_cases", "resolved_cases"] + DURATION_COLS


def build_performance(active: pd.DataFrame, duration: pd.DataFrame, group_col: str) -> pd.DataFrame:
    # 1. Merge ONLY on the group_col (court_id or circuit)
    # This keeps all historical quarters and attaches the "current" active count
    perf = duration.merge(active, on=group_col, how="left")

    # 2. Fill potential missing active counts with 0
    perf["active_cases"] = perf["active_cases"].fillna(0).astype(int)
    
    # 3. Clean up duration metrics
    existing_dur = [c for c in DURATION_COLS if c in perf.columns]
    perf[existing_dur] = perf[existing_dur].fillna(0).round(2)

    return perf.sort_values([group_col, "year_quarter_terminated"]).reset_index(drop=True)


def main():
    print("Processing court performance metrics...")
    active_c = pd.read_parquet(paths["active_courts"])
    duration_c = pd.read_parquet(paths["duration_court"])
    build_performance(active_c, duration_c, "court_id").to_parquet(paths["out_court"], index=False)

    print("Processing circuit performance metrics...")
    active_circ = pd.read_parquet(paths["active_circuit"])
    duration_circ = pd.read_parquet(paths["duration_circuit"])
    build_performance(active_circ, duration_circ, "circuit").to_parquet(paths["out_circuit"], index=False)


if __name__ == "__main__":
    main()
