from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent.parent

INPUT_PATH = (
    BASE_DIR
    / "gold"
    / "metrics"
    / "case_metrics.parquet"
)

OUTPUT_PATH = (
    BASE_DIR
    / "gold"
    / "metrics"
    / "case_duration_distribution.parquet"
)


def main():

    df = pd.read_parquet(INPUT_PATH)

    # keep only resolved cases
    resolved = df[
        df["duration_days"].notna()
    ].copy()

    duration_metrics = (
        resolved
        .groupby("court_id")["duration_days"]
        .agg(
            resolved_cases="count",
            mean_duration="mean",
            median_duration="median",
            std_duration="std",
            min_duration="min",
            max_duration="max"
        )
        .reset_index()
    )

    # percentiles
    p75 = (
        resolved
        .groupby("court_id")["duration_days"]
        .quantile(0.75)
        .reset_index(name="p75_duration")
    )

    p90 = (
        resolved
        .groupby("court_id")["duration_days"]
        .quantile(0.90)
        .reset_index(name="p90_duration")
    )

    duration_metrics = (
        duration_metrics
        .merge(p75, on="court_id", how="left")
        .merge(p90, on="court_id", how="left")
    )

    # rounding
    numeric_cols = duration_metrics.select_dtypes(
        include="number"
    ).columns

    duration_metrics[numeric_cols] = (
        duration_metrics[numeric_cols]
        .round(2)
    )

    duration_metrics.to_parquet(
        OUTPUT_PATH,
        index=False
    )

    print("Duration metrics exported.\n")

    print(duration_metrics)


if __name__ == "__main__":
    main()