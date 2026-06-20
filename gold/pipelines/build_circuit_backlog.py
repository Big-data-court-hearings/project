"""
Backlog evolution metrics engine.

Merges quarterly inflow/outflow, anchors on a 2022-Q4 baseline via DuckDB
array vectors, and computes true cumulative backlog evolution per circuit.

Produces:
- metrics/backlog_evolution_by_quarter.parquet
"""

import pandas as pd
from pathlib import Path
from _common import GOLD_PATH, connect_gold, ensure

INFLOW_PATH  = GOLD_PATH / "case_inflow_by_quarter.parquet"
OUTFLOW_PATH = GOLD_PATH / "case_outflow_by_quarter.parquet"
OUTPUT_PATH  = ensure(GOLD_PATH /"backlog_evolution_circuit_by_quarter.parquet")


def get_baseline() -> dict:
    """Cases active at end of 2022-Q4 per circuit, using activity_quarters array."""
    con = connect_gold(read_only=True)
    df = con.execute(f"""
    SELECT circuit, COUNT(*) AS baseline_load
    FROM gold.case_metrics
    WHERE list_contains(activity_quarters, '2023-q1') AND circuit IS NOT NULL
    GROUP BY circuit
    """).df()
    return dict(zip(df["circuit"], df["baseline_load"]))


def main():
    print("Reading quarterly inflow/outflow...")
    inflow  = pd.read_parquet(INFLOW_PATH).rename(columns={"year_quarter_filed": "year_quarter"})
    outflow = pd.read_parquet(OUTFLOW_PATH).rename(columns={"year_quarter_terminated": "year_quarter"})

    backlog = (
        pd.merge(inflow, outflow, on=["year_quarter", "circuit"], how="outer")
        .pipe(lambda d: d[d["year_quarter"].str[:4].astype(int) > 2022])
        .assign(
            inflow=lambda d: d["inflow"].fillna(0).astype(int),
            outflow=lambda d: d["outflow"].fillna(0).astype(int),
        )
        .sort_values(["circuit", "year_quarter"])
        .reset_index(drop=True)
    )

    backlog["net_change"] = backlog["inflow"] - backlog["outflow"]
    # Add to your backlog processing script
    baseline = get_baseline()
    backlog["backlog"] = (
        backlog["circuit"].map(baseline).fillna(0).astype(int)
        + backlog.groupby("circuit")["net_change"].cumsum()
    )
    backlog["clearance_efficiency"] = backlog["outflow"] / backlog["backlog"].replace(0, 1) 
    backlog["backlog_clearance_ratio"] = backlog["outflow"] / backlog["inflow"].replace(0, None)    
    backlog = backlog.drop(columns=["avg_resolution_days_y", "avg_resolution_days_x"])
    backlog = backlog.dropna()
    backlog.to_parquet(OUTPUT_PATH, index=False)

    


if __name__ == "__main__":
    main()
