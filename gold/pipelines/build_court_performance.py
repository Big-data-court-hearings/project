from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent.parent

ACTIVE_PATH = (
    BASE_DIR
    / "gold"
    / "metrics"
    / "active_cases_by_court.parquet"
)

DURATION_PATH = (
    BASE_DIR
    / "gold"
    / "metrics"
    / "case_duration_distribution.parquet"
)

CIRCUIT_PATH = (
    BASE_DIR
    / "gold"
    / "metrics"
    / "metrics_by_circuit.parquet"
)

OUTPUT_PATH = (
    BASE_DIR
    / "gold"
    / "metrics"
    / "court_performance_metrics.parquet"
)

OUTPUT_CIRCUIT_PATH = (
    BASE_DIR
    / "gold"
    / "metrics"
    / "circuit_performance_metrics.parquet"
)


def process_metrics(active, duration, group_col):
    # harmonize possible column names
    if "avg_resolution_days" in duration.columns:
        duration = duration.rename(columns={"avg_resolution_days": "mean_duration"})

    if "active_cases" not in active.columns:

        possible_cols = [
            c for c in active.columns
            if c != group_col and c != "mean_duration"
        ]

        if len(possible_cols) == 1:
            active = active.rename(columns={
                possible_cols[0]: "active_cases"
            })

    if active.equals(duration):
        performance = active.copy()
    else:
        performance = active.merge(
            duration,
            on=group_col,
            how="left"
        )

    # fill missing resolved cases
    if "resolved_cases" in performance.columns:
        performance["resolved_cases"] = (
            performance["resolved_cases"]
            .fillna(0)
            .astype(int)
        )

    # fill missing duration metrics
    duration_cols = [
        "mean_duration",
        "median_duration",
        "std_duration",
        "min_duration",
        "max_duration",
        "p75_duration",
        "p90_duration"
    ]

    existing_duration_cols = [
        c for c in duration_cols
        if c in performance.columns
    ]

    performance[existing_duration_cols] = (
        performance[existing_duration_cols]
        .fillna(0)
        .round(2)
    )

    # reorder columns
    desired_order = [
        group_col,
        "active_cases",
        "resolved_cases",
        "mean_duration",
        "median_duration",
        "std_duration",
        "min_duration",
        "max_duration",
        "p75_duration",
        "p90_duration"
    ]

    existing_cols = [
        c for c in desired_order
        if c in performance.columns
    ]

    performance = performance[existing_cols]

    # sort by workload
    if "active_cases" in performance.columns:
        performance = performance.sort_values(
            by="active_cases",
            ascending=False
        )
        
    return performance


def main():

    # ============================================================
    # COURT METRICS
    # ============================================================

    active = pd.read_parquet(ACTIVE_PATH)

    duration = pd.read_parquet(DURATION_PATH)

    performance = process_metrics(active, duration, "court_id")

    performance.to_parquet(
        OUTPUT_PATH,
        index=False
    )

    print("Court performance metrics exported.\n")

    print(performance.head(20))

    # ============================================================
    # CIRCUIT METRICS
    # ============================================================

    print("\n" + "="*50 + "\n")
    print("Processing Circuit performance metrics...")

    circuit_data = pd.read_parquet(CIRCUIT_PATH)

    circuit_performance = process_metrics(circuit_data, circuit_data, "circuit")

    circuit_performance.to_parquet(
        OUTPUT_CIRCUIT_PATH,
        index=False
    )

    print("Circuit performance metrics exported.\n")

    print(circuit_performance.head(20))


if __name__ == "__main__":
    main()