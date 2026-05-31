from pathlib import Path
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent.parent

BACKLOG_PATH = (
    BASE_DIR
    / "gold"
    / "metrics"
    / "backlog_by_quarter.parquet"
)

OUTPUT_PATH = (
    BASE_DIR
    / "gold"
    / "metrics"
    / "clearance_rate_by_year.parquet"
)


def main():

    df = pd.read_parquet(BACKLOG_PATH)

    df["clearance_rate"] = np.where(
        (df["outflow"] >0) & (df["inflow"]>0),
        df["outflow"] / df["inflow"],
        np.nan
    )

    df["clearance_rate_pct"] = (
        df["clearance_rate"] * 100
    ).round(2)

    result = df[[
        "year_quarter",
        "inflow",
        "outflow",
        "clearance_rate",
        "clearance_rate_pct"
    ]]

    result.to_parquet(
        OUTPUT_PATH,
        index=False
    )

    print("Clearance rate metrics exported.\n")

    print(result)


if __name__ == "__main__":
    main()