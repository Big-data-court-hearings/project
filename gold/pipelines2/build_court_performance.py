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
    "active":           GOLD_PATH / "active_cases_by_court.parquet",
    "duration_court":   GOLD_PATH / "case_duration_distribution_court_by_quarter.parquet",
    "circuit":          GOLD_PATH / "metrics_by_circuit.parquet",
    "out_court":        ensure(GOLD_PATH / "court_performance_metrics.parquet"),
    "out_circuit":      ensure(GOLD_PATH / "circuit_performance_metrics.parquet"),
}

DURATION_COLS = ["mean_duration", "median_duration", "std_duration", "min_duration", "max_duration", "p75_duration", "p90_duration"]
DESIRED_ORDER  = ["active_cases", "resolved_cases"] + DURATION_COLS


def build_performance(active: pd.DataFrame, duration: pd.DataFrame, group_col: str, time_col: str) -> pd.DataFrame:
    if "avg_resolution_days" in duration.columns:
        duration = duration.rename(columns={"avg_resolution_days": "mean_duration"})

    if "active_cases" not in active.columns:
        candidates = [c for c in active.columns if c not in (group_col, time_col, "mean_duration")]
        if len(candidates) == 1:
            active = active.rename(columns={candidates[0]: "active_cases"})

    if active.equals(duration):
        perf = active.copy()
    else:
        keys = [group_col] + ([time_col] if time_col in active.columns and time_col in duration.columns else [])
        perf = active.merge(duration, on=keys, how="left")

    if "resolved_cases" in perf.columns:
        perf["resolved_cases"] = perf["resolved_cases"].fillna(0).astype(int)

    existing_dur = [c for c in DURATION_COLS if c in perf.columns]
    perf[existing_dur] = perf[existing_dur].fillna(0).round(2)

    col_order = [group_col, time_col] + [c for c in DESIRED_ORDER if c in perf.columns]
    perf = perf[[c for c in col_order if c in perf.columns]]

    sort_keys = [group_col] + ([time_col] if time_col in perf.columns else [])
    return perf.sort_values(sort_keys).reset_index(drop=True)


def main():
    print("Processing court performance metrics...")
    active   = pd.read_parquet(paths["active"])
    duration = pd.read_parquet(paths["duration_court"])
    build_performance(active, duration, "court_id", "year_quarter_filed").to_parquet(paths["out_court"], index=False)
    print(f"Exported: {paths['out_court']}")

    print("Processing circuit performance metrics...")
    circuit_data = pd.read_parquet(paths["circuit"])
    time_col = "year_quarter_filed" if "year_quarter_filed" in circuit_data.columns else "year_quarter"
    build_performance(circuit_data, circuit_data, "circuit", time_col).to_parquet(paths["out_circuit"], index=False)
    print(f"Exported: {paths['out_circuit']}")


if __name__ == "__main__":
    main()
