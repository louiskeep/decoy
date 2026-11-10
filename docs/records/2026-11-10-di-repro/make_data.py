"""Write the four CSV inputs for the 2026-11-10 distribution-model QA re-test.

Usage: python make_data.py OUTDIR
Each file uses its own random.Random(seed), so the bytes are the same on every run.
"""

import csv
import datetime as dt
import math
import random
import sys
from pathlib import Path


def write(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def c1(out):
    # Two unrelated numeric columns and two unrelated category columns.
    r = random.Random(5)
    rows = []
    for _ in range(2000):
        rows.append([
            round(r.gauss(50, 10), 2),
            round(r.gauss(50, 10), 2),
            r.choices("ABCD", weights=[4, 3, 2, 1])[0],
            r.choices("WXYZ", weights=[4, 3, 2, 1])[0],
        ])
    write(out / "c1.csv", ["a", "b", "cat1", "cat2"], rows)


def types(out):
    r = random.Random(21)
    rows = []
    start = dt.date(2021, 1, 1)
    for i in range(20000):
        null10 = "" if r.random() < 0.10 else round(r.gauss(50, 10), 3)
        null90 = "" if r.random() < 0.90 else r.choice("ABC")
        age = r.randint(18, 90)
        skew = round(r.lognormvariate(3, 1.2), 3)
        bimodal = round(r.gauss(20, 3) if r.random() < 0.5 else r.gauss(80, 3), 3)
        outlier = 1_000_000 if i == 0 else round(r.gauss(100, 15), 3)
        price = r.choice([9.99, 19.99, 49.99, 99.99])
        year = 2021 + r.randrange(3)
        month = 1 if r.random() < 0.64 else r.randint(1, 12)
        day = dt.date(year, month, r.randint(1, 28))
        bit = r.randint(0, 1)
        zipc = f"{r.randint(0, 99999):05d}"
        rows.append([null10, null90, age, skew, bimodal, outlier, price, day.isoformat(), bit, zipc])
    write(out / "types.csv",
          ["null10", "null90", "age", "skew", "bimodal", "outlier", "price", "day", "bit", "zip"], rows)


def cond(out):
    # 12 parents with skewed weights; each allows three of six kids with weights 6, 3, 1.
    r = random.Random(11)
    parents = [f"P{i:02d}" for i in range(12)]
    pweights = [20, 15, 12, 10, 9, 8, 7, 6, 5, 4, 3, 1]
    kids = [f"K{i}" for i in range(6)]
    allowed = {p: r.sample(kids, 3) for p in parents}
    rows = []
    for _ in range(6000):
        p = r.choices(parents, weights=pweights)[0]
        k = r.choices(allowed[p], weights=[6, 3, 1])[0]
        rows.append([p, k])
    write(out / "cond.csv", ["parent", "kid"], rows)


def leak(out):
    # One unique diagnosis code, one extreme salary, and 30 short notes naming people.
    r = random.Random(31)
    codes = ["E11.9", "I10", "J45.909", "M54.5", "F41.1", "K21.9", "E78.5", "N39.0"]
    states = ["CA", "TX", "NY", "FL", "WA"]
    rows = []
    for i in range(1000):
        diag = "RARE-HIV-B20" if i == 17 else r.choice(codes)
        salary = 987654 if i == 42 else round(r.gauss(60000, 12000))
        note = f"note: patient Surname{r.randrange(30)} called"
        rows.append([i + 1, r.choice(states), diag, salary, note])
    write(out / "leak.csv", ["id", "state", "diagnosis", "salary", "note"], rows)


if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for fn in (c1, types, cond, leak):
        fn(out)
