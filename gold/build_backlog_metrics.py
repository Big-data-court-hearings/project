from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent

INFLOW_PATH = BASE_DIR / "gold" / "case_inflow_by_year.parquet"
OUTFLOW_PATH = BASE_DIR / "gold" / "case_outflow_by_year.parquet"

OUTPUT_PATH = BASE_DIR / "gold" / "backlog_by_year.parquet"


def main():

    inflow = pd.read_parquet(INFLOW_PATH)
    outflow = pd.read_parquet(OUTFLOW_PATH)

    inflow = inflow.rename(columns={
        "year_filed": "year",
        "filed_cases": "inflow"
    })

    outflow = outflow.rename(columns={
        "year_terminated": "year",
        "terminated_cases": "outflow"
    })

    min_year = int(min(
        inflow["year"].min(),
        outflow["year"].min()
    ))

    max_year = int(max(
        inflow["year"].max(),
        outflow["year"].max()
    ))

    years = pd.DataFrame({
        "year": range(min_year, max_year + 1)
    })

    backlog = (
        years
        .merge(inflow, on="year", how="left")
        .merge(outflow, on="year", how="left")
    )

    backlog["inflow"] = backlog["inflow"].fillna(0).astype(int)
    backlog["outflow"] = backlog["outflow"].fillna(0).astype(int)

    backlog["cumulative_inflow"] = backlog["inflow"].cumsum()
    backlog["cumulative_outflow"] = backlog["outflow"].cumsum()

    backlog["backlog"] = (
        backlog["cumulative_inflow"]
        - backlog["cumulative_outflow"]
    )

    backlog.to_parquet(OUTPUT_PATH, index=False)

    print("Backlog metrics exported.\n")

    print(backlog)


if __name__ == "__main__":
    main()