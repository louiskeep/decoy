"""Print the measurements for each finding from the outputs of run.sh. Usage: python measure.py DIR"""

import csv
import json
import statistics as st
import sys
from collections import Counter
from pathlib import Path

d = Path(sys.argv[1])


def rows(name):
    with open(d / name, newline="") as f:
        return list(csv.DictReader(f))


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def corr(x, y):
    mx, my = st.mean(x), st.mean(y)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sx = sum((a - mx) ** 2 for a in x) ** 0.5
    sy = sum((b - my) ** 2 for b in y) ** 0.5
    return sxy / (sx * sy)


def out(key, value):
    print(f"{key}: {value}")


# C1
r = rows("out/c1_ident.csv")
for p in ("stat", "fn", "cat", "int", "date"):
    same = sum(1 for x in r if x[f"{p}_a"] == x[f"{p}_b"]) / len(r)
    out(f"C1 identical {p} equal-row share", round(same, 3))
r = rows("out/c1_indep.csv")
out("C1 indep corr(a,b)", round(corr([float(x["a"]) for x in r], [float(x["b"]) for x in r]), 3))
out("C1 indep cat1==cat2 index share", round(sum(1 for x in r if "ABCD".index(x["cat1"]) == "WXYZ".index(x["cat2"])) / len(r), 3))
src = rows("c1.csv")
out("C1 source corr(a,b)", round(corr([float(x["a"]) for x in src], [float(x["b"]) for x in src]), 3))

# Types file: C2, H2, H3, M3, M4. PREFIX="" is the CLI fit, "doc_" the engine document fit.
PREFIX = sys.argv[2] if len(sys.argv) > 2 else ""
print("=== types section, prefix", repr(PREFIX))
s, g = rows("types.csv"), rows(f"out/{PREFIX}types_out.csv")


def nullrate(rs, c):
    return round(sum(1 for x in rs if x[c] in ("", None)) / len(rs), 4)


for c in ("null10", "null90"):
    out(f"H2 {c} null rate source/gen", (nullrate(s, c), nullrate(g, c)))
for c in ("outlier", "skew", "bimodal", "price", "age"):
    sv = [num(x[c]) for x in s if num(x[c]) is not None]
    gv = [num(x[c]) for x in g if num(x[c]) is not None]
    out(f"{c} mean source/gen", (round(st.mean(sv), 2), round(st.mean(gv), 2)))
    out(f"{c} median source/gen", (round(st.median(sv), 2), round(st.median(gv), 2)))
    out(f"{c} distinct source/gen", (len(set(sv)), len(set(gv))))
sv = [num(x["outlier"]) for x in s]
gv = [num(x["outlier"]) for x in g if num(x["outlier"]) is not None]
out("C2 outlier share >200 source/gen", (round(sum(v > 200 for v in sv) / len(sv), 5), round(sum(v > 200 for v in gv) / len(gv), 4)))
gp = [num(x["price"]) for x in g if num(x["price"]) is not None]
out("H3 price share on a real price", round(sum(v in (9.99, 19.99, 49.99, 99.99) for v in gp) / len(gp), 4))
out("H3 price decimals in gen (max)", max(len(x["price"].split(".")[1]) if "." in x["price"] else 0 for x in g if x["price"]))
for rs, tag in ((s, "source"), (g, "gen")):
    v = [num(x["bimodal"]) for x in rs if num(x["bimodal"]) is not None]
    out(f"H3 bimodal gap (35..65) share {tag}", round(sum(35 < a < 65 for a in v) / len(v), 4))
sd = [x["day"] for x in s if x["day"]]
gd = [x["day"] for x in g if x["day"]]
out("M3 day sample gen", gd[:3])
out("M3 January share source/gen", (round(sum(x[5:7] == "01" for x in sd) / len(sd), 3), round(sum(x[5:7] == "01" for x in gd) / len(gd), 3)))
out("M3 gen values with a time part", round(sum((" " in x or "T" in x) for x in gd) / len(gd), 3))
out("M3 year mix source", sorted(Counter(x[:4] for x in sd).items()))
out("M3 year mix gen", sorted(Counter(x[:4] for x in gd).items()))
out("M4 zip shorter than 5 chars (gen)", round(sum(len(x["zip"]) < 5 for x in g if x["zip"]) / len(g), 4))
out("M4 zip sample gen", [x["zip"] for x in g[:5]])
out("bit values gen", sorted(Counter(x["bit"] for x in g).items()))

# null_probability on top of a fitted null rate
n = rows(f"out/{PREFIX}np_check.csv")
for c in ("fitted", "np_0", "np_10", "np_50"):
    out(f"null_probability check {c} null rate", nullrate(n, c))

# C3 fidelity report
try:
    rep = json.loads((d / "out/fidelity.json").read_text())
    print("C3 fidelity json top-level keys:", list(rep)[:20])
    print(json.dumps(rep, indent=1)[:6000])
except Exception as e:  # report is printed whole for reading by hand
    print("C3 fidelity json unreadable:", e)

# H1
src = rows("cond.csv")
pairs = {(x["parent"], x["kid"]) for x in src}
g = rows("out/cond_out.csv")
bad = sum(1 for x in g if (x["parent"], x["kid"]) not in pairs)
out("H1 source pairs", len(pairs))
out("H1 generated rows with an unseen pair", (bad, round(bad / len(g), 4)))
snap = json.loads((d / "cond.snapshot.json").read_text())
j = snap["joints"][0]
out("H1 joint cells stored / distinct pairs / other_count", (len(j["cells"]), j.get("cell_count"), j.get("other_count")))
stored_parents = {c["key"][j["columns"].index("parent")] for c in j["cells"]}
out("H1 parents with no stored cell", sorted({x["parent"] for x in src} - stored_parents))
out("H1 unseen-pair rows by parent", sorted(Counter(x["parent"] for x in g if (x["parent"], x["kid"]) not in pairs).items()))

# H6, H7
LEAK = "leak_doc" if PREFIX else "leak"
snap = json.loads((d / f"{LEAK}.snapshot.json").read_text())
print("=== leak section", LEAK, "value_policy", snap.get("value_policy"), "redacted", snap.get("redacted_columns"))
cols = snap.get("columns", snap)
for c in ("diagnosis", "salary", "note", "state"):
    print(f"H6/H7 snapshot {c}:", json.dumps(cols.get(c), indent=None)[:900])
try:
    g = rows(f"out/{PREFIX}leak_out.csv")
    out("H6 RARE-HIV-B20 rows in gen", sum(1 for x in g if x["diagnosis"] == "RARE-HIV-B20"))
    sal = [num(x["salary"]) for x in g if num(x["salary"]) is not None]
    out("H6 salary max gen", max(sal) if sal else None)
    real = {x["note"] for x in rows("leak.csv")}
    out("H7 gen notes that are real source strings", round(sum(x["note"] in real for x in g) / len(g), 3))
    out("H7 gen note sample", [x["note"] for x in g[:3]])
except FileNotFoundError:
    out("H6/H7 generation", "no output file (see leak_run.txt)")
