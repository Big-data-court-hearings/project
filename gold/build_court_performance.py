from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent

ACTIVE_PATH = (
    BASE_DIR / "gold" / "active_cases_by_court.parquet"
)

DURATION_PATH = (
    BASE_DIR / "gold" / "case_duration_distribution.parquet"
)

OUTPUT_PATH = (
    BASE_DIR / "gold" / "court_performance_metrics.parquet"
)


def main():

    active = pd.read_parquet(ACTIVE_PATH)

    duration = pd.read_parquet(DURATION_PATH)

    # harmonize possible column names
    if "active_cases" not in active.columns:

        possible_cols = [
            c for c in active.columns
            if c != "court_id"
        ]

        if len(possible_cols) == 1:
            active = active.rename(columns={
                possible_cols[0]: "active_cases"
            })

    performance = active.merge(
        duration,
        on="court_id",
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
        "court_id",
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

    performance.to_parquet(
        OUTPUT_PATH,
        index=False
    )

    print("Court performance metrics exported.\n")

    print(performance.head(20))


if __name__ == "__main__":
    main()