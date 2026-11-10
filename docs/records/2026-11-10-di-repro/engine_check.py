"""Engine-level half of the re-test, for fixes whose CLI half has not merged yet.

`decoy fit` on CLI main still calls `compute_distribution_snapshot` without `cell_format` or
value redaction. The engine call those CLI halves will use is `distribution_snapshot_document`.
This script writes snapshots through it so the sampler fixes (#434, #436) and the redaction
(#420) can be measured with `decoy run`, and scores fidelity through `compute_fidelity` (#438)
because `decoy report fidelity` on CLI main cannot read a CSV with engine main.

Usage: python engine_check.py snapshots   (in the run.sh work directory)
       python engine_check.py fidelity
"""

import json
import sys

import pandas as pd
from decoy_engine import distribution_snapshot_document
from decoy_engine.quality.fidelity import compute_fidelity
from decoy_engine.quality.snapshot import compute_distribution_snapshot


def dump(doc, path):
    with open(path, "w") as f:
        json.dump(doc, f, indent=1, default=str)


def snapshots():
    types = pd.read_csv("types.csv", parse_dates=["day"])
    # include_values keeps every value, so only the cell_format block differs from the CLI fit.
    dump(distribution_snapshot_document(types, include_values=True), "types_doc.snapshot.json")
    leak = pd.read_csv("leak.csv")
    doc = distribution_snapshot_document(leak, source_label="leak.csv")
    print("leak value_policy:", doc.get("value_policy"), "redacted:", doc.get("redacted_columns"))
    dump(doc, "leak_doc.snapshot.json")


def fidelity():
    src = pd.read_csv("types.csv", parse_dates=["day"])
    for name in ("out/types_out.csv", "out/doc_types_out.csv"):
        gen = pd.read_csv(name, parse_dates=["day"])
        rep = compute_fidelity(compute_distribution_snapshot(src), compute_distribution_snapshot(gen))
        print(f"== fidelity {name}: overall {rep['overall_score']}")
        for c in rep["marginal"]["columns"]:
            keep = {k: c.get(k) for k in ("similarity", "method", "comparable", "value_similarity",
                                          "missing_value_similarity", "snapshot_null_fraction")}
            print(f"  {c['column']}: {keep}")


if __name__ == "__main__":
    {"snapshots": snapshots, "fidelity": fidelity}[sys.argv[1]]()
