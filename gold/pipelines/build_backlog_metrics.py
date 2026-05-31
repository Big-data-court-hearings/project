from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent.parent

INFLOW_PATH = (
    BASE_DIR
    / "gold"
    / "metrics"
    / "case_inflow_by_quarter.parquet"
)

OUTFLOW_PATH = (
    BASE_DIR
    / "gold"
    / "metrics"
    / "case_outflow_by_quarter.parquet"
)

OUTPUT_PATH = (
    BASE_DIR
    / "gold"
    / "metrics"
    / "backlog_by_quarter.parquet"
)


def main():
    # Read the datasets
    inflow = pd.read_parquet(INFLOW_PATH)
    outflow = pd.read_parquet(OUTFLOW_PATH)

    # 🛠️ FIX: Renamed 'filed_cases' to 'inflow' (matches what your inflow query generates)
    inflow = inflow.rename(columns={
        "year_quarter_filed": "year_quarter",
        "filed_cases": "inflow" 
    })

    outflow = outflow.rename(columns={
        "year_quarter_terminated": "year_quarter",
        "terminated_cases": "outflow"
    })

    # 🛠️ FIX: Merge inflow and outflow directly using an 'outer' join.
    # This guarantees you get all quarters without needing a placeholder 'years' dataframe.
    backlog = pd.merge(inflow, outflow, on="year_quarter", how="outer")

    # Sort chronologically so cumulative sum (cumsum) calculates correctly
    backlog = backlog.sort_values("year_quarter").reset_index(drop=True)

    # Replace missing values with zero
    backlog["inflow"] = backlog["inflow"].fillna(0).astype(int)
    backlog["outflow"] = backlog["outflow"].fillna(0).astype(int)

    # Cumulative calculations
    backlog["cumulative_inflow"] = backlog["inflow"].cumsum()
    backlog["cumulative_outflow"] = backlog["outflow"].cumsum()

    # Net Backlog calculation
    backlog["backlog"] = (
        backlog["cumulative_inflow"]
        - backlog["cumulative_outflow"]
    )

    # Optional: Filter down to your specific observatory target timeline if needed
    # e.g., backlog = backlog[backlog["year_quarter"].str.startswith(('2025', '2026'))]

    # Export to Parquet
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    backlog.to_parquet(OUTPUT_PATH, index=False)

    print("Backlog metrics exported successfully.\n")
    print(backlog)


if __name__ == "__main__":
    main()