"""
Backlog evolution metrics engine.

Merges quarterly inflow/outflow, anchors on a 2022-Q4 baseline via DuckDB
array vectors, and computes true cumulative backlog evolution per circuit.

Produces:
- metrics/backlog_evolution_by_quarter.parquet
"""

import pandas as pd
from pathlib import Path
from _common import GOLD_PATH, connect, ensure

CASE_METRICS_PATH = GOLD_PATH / "case_enhanced.parquet"
INFLOW_PATH  = GOLD_PATH / "case_inflow_by_quarter.parquet"
OUTFLOW_PATH = GOLD_PATH / "case_outflow_by_quarter.parquet"
OUTPUT_PATH  = ensure(GOLD_PATH /"backlog_evolution_by_quarter.parquet")


def get_baseline() -> dict:
    """Cases active at end of 2022-Q4 per circuit, using activity_quarters array."""
    con = connect()
    df = con.execute(f"""
    SELECT circuit, COUNT(*) AS baseline_load
    FROM read_parquet('{CASE_METRICS_PATH.as_posix()}')
    WHERE list_contains(activity_quarters, '2022-q4') AND circuit IS NOT NULL
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

    baseline = get_baseline()
    backlog["backlog"] = (
        backlog["circuit"].map(baseline).fillna(0).astype(int)
        + backlog.groupby("circuit")["net_change"].cumsum()
    )

    backlog.to_parquet(OUTPUT_PATH, index=False)
    print(f"Exported: {OUTPUT_PATH}")
    print(backlog.to_string(index=False))


if __name__ == "__main__":
    main()
