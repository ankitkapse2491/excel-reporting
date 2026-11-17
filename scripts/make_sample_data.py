"""Generate synthetic sample data (fake PII only) for demos and tests."""

from __future__ import annotations

import argparse
import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

REGIONS = ["North", "South", "East", "West"]
PRODUCTS = ["Widget", "Gadget", "Gizmo", "Doohickey"]


def make(rows: int = 500, seed: int = 42) -> pd.DataFrame:
    rnd = random.Random(seed)  # noqa: S311 - synthetic data, not security-relevant
    start = date(2025, 1, 1)
    records = []
    for i in range(rows):
        qty = rnd.randint(1, 20)
        price = round(rnd.uniform(5, 250), 2)
        records.append(
            {
                "Order ID": 1000 + i,
                "Order Date": (start + timedelta(days=rnd.randint(0, 364))).isoformat(),
                "Customer Name": f"Test Customer {rnd.randint(1, 80)}",
                "Customer Email": f"user{rnd.randint(1, 80)}@example.com",
                "Phone": f"+1-555-01{rnd.randint(0, 99):02d}",
                "Region": rnd.choice(REGIONS),
                "Product": rnd.choice(PRODUCTS),
                "Quantity": qty,
                "Unit Price": price,
                "Revenue": round(qty * price, 2),
            }
        )
    df = pd.DataFrame(records)
    df = pd.concat([df, df.head(5)], ignore_index=True)  # duplicates to exercise cleaning
    df.loc[3, "Revenue"] = None
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("data/input/sales.csv"))
    ap.add_argument("--rows", type=int, default=500)
    ns = ap.parse_args()
    ns.out.parent.mkdir(parents=True, exist_ok=True)
    make(ns.rows).to_csv(ns.out, index=False)
    print(f"wrote {ns.out}")
