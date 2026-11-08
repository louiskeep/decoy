"""Write a fixed-seed four-column source as Parquet and CSV in bounded batches.

Same columns as the engine's `scripts/bench-auto-chunk/bench_worker_lazy.py` native workload
(hash, redact, truncate, passthrough), so CLI and engine numbers compare.
Usage: gen.py ROWS OUT_DIR
"""

import json
import sys
from pathlib import Path

import numpy
import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

BATCH = 1_048_576


def chunk(rng: numpy.random.Generator, rows: int) -> pa.Table:
    ks = rng.integers(0, 10**9, size=rows, dtype=numpy.int64).tolist()
    cols = {
        "email": [f"user{v:09d}@example.com" for v in ks],
        "secret": [f"secret-{v:09d}" for v in ks],
        "zip": [f"{v:09d}" for v in ks],
        "ref": [f"keep-{v:09d}" for v in ks],
    }
    return pa.table({n: pa.array(v, pa.string()) for n, v in cols.items()})


def main() -> None:
    rows, out = int(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    rng = numpy.random.default_rng(20261108)
    pw = cw = None
    done = nbytes = 0
    while done < rows:
        t = chunk(rng, min(BATCH, rows - done))
        nbytes += t.nbytes
        if pw is None:
            pw = pq.ParquetWriter(out / "t.parquet", t.schema)
            cw = pacsv.CSVWriter(out / "t.csv", t.schema)
        pw.write_table(t, row_group_size=BATCH)
        cw.write_table(t)
        done += t.num_rows
    pw.close()
    cw.close()
    print(json.dumps({"rows": rows, "arrow_nbytes": nbytes,
                      "parquet_bytes": (out / "t.parquet").stat().st_size,
                      "csv_bytes": (out / "t.csv").stat().st_size}))


if __name__ == "__main__":
    main()
