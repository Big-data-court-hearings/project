"""
Quarterly clearance rate metrics by circuit.

Produces:
- metrics/clearance_rate_by_quarter.parquet
"""

import numpy as np
import pandas as pd
from _common import GOLD_PATH, ensure, START_YEAR

BACKLOG_PATH = GOLD_PATH /  "backlog_evolution_circuit_by_quarter.parquet"
OUTPUT_PATH  = ensure(GOLD_PATH /"clearance_rate_circuit_by_quarter.parquet")


def main():
    df = (
        pd.read_parquet(BACKLOG_PATH)
        .pipe(lambda d: d[d["year_quarter"].str[:4].astype(int) > START_YEAR])
        .copy()
    )

    df["backlog_clearance_rate"] = np.where(
        (df["inflow"] > 0) & (df["outflow"] > 0),
        df["outflow"] / df["inflow"],
        np.nan,
    )
    df["backlog_clearance_rate_pct"] = (df["backlog_clearance_rate"] * 100).round(2)

    result = (
        df[["year_quarter", "circuit", "inflow", "outflow", "backlog_clearance_rate", "backlog_clearance_rate_pct"]]
        .sort_values(["circuit", "year_quarter"])
        .reset_index(drop=True)
    )

    result.to_parquet(OUTPUT_PATH, index=False)
    print(f"Exported: {OUTPUT_PATH}")
    print(result.to_string(index=False))


if __name__ == "__main__":
    main()
