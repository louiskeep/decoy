"""Run `decoy run` end to end over gen.py sources and record wall time and peak RSS.

Each cell is a fresh `/usr/bin/time -v python -m decoy run CONFIG [--chunked]` process.
Usage: drive.py OUT_JSONL WORK_DIR SIZES (comma list, e.g. 1000000,4000000)
Env THREAD_CELLS=1 adds plain-run cells with OMP_NUM_THREADS=1 and =8 (Arrow's CPU pool).
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
COLUMNS = """      - {name: email, strategy: hash, namespace: bench_ns}
      - {name: secret, strategy: redact}
      - {name: zip, strategy: truncate, provider_config: {length: 3, keep: head}}
      - {name: ref, strategy: passthrough}"""


def config(src: Path, fmt: str, out: Path) -> str:
    header = "\n    has_header: true" if fmt == "csv" else ""
    return f"""version: 2
global_settings:
  seed: 42
sources:
  t:
    type: file
    format: {fmt}
    path: {src}{header}
tables:
  - name: t
    columns:
{COLUMNS}
targets:
  t:
    type: file
    format: parquet
    path: {out}
"""


def cell(py: str, cfg: Path, chunked: bool, env_extra: dict[str, str]) -> dict:
    cmd = ["/usr/bin/time", "-v", py, "-m", "decoy", "run", str(cfg), "--mask-secret", "env:DECOY_MASK_SECRET"]
    if chunked:
        cmd.append("--chunked")
    env = dict(os.environ, DECOY_MASK_SECRET="ab" * 32, **env_extra)
    t0 = time.perf_counter()
    p = subprocess.run(cmd, capture_output=True, text=True, env=env)
    wall = time.perf_counter() - t0
    m = re.search(r"Maximum resident set size \(kbytes\): (\d+)", p.stderr)
    route = re.search(r"Route\W+([^\n]+)", p.stdout + p.stderr)
    return {"rc": p.returncode, "wall_s": round(wall, 2),
            "peak_rss_mb": round(int(m.group(1)) / 1024, 1) if m else None,
            "route": route.group(1).strip(" \u2502") if route else None,
            "tail": [ln for ln in (p.stdout + p.stderr).splitlines() if ln.strip() and not ln.startswith("\t")][-3:] if p.returncode else []}


def main() -> None:
    out_jsonl, work, sizes = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    py = sys.executable
    for rows in [int(s) for s in sizes.split(",")]:
        d = work / f"r{rows}"
        gen = subprocess.run([py, str(HERE / "gen.py"), str(rows), str(d)],
                             capture_output=True, text=True, check=True)
        facts = json.loads(gen.stdout.strip().splitlines()[-1])
        plans = [(fmt, chunked, {}) for fmt in ("parquet", "csv") for chunked in (False, True)]
        if os.environ.get("THREAD_CELLS"):
            plans += [("parquet", False, {"OMP_NUM_THREADS": n}) for n in ("1", "8")]
        for fmt, chunked, env_extra in plans:
            cfg = d / f"cfg-{fmt}-{int(chunked)}.yaml"
            target = d / f"out-{fmt}-{int(chunked)}.parquet"
            cfg.write_text(config(d / f"t.{fmt}", fmt, target))
            rec = {**facts, "format": fmt, "chunked": chunked, **env_extra,
                   **cell(py, cfg, chunked, env_extra)}
            with out_jsonl.open("a") as fh:
                fh.write(json.dumps(rec) + "\n")
            print(json.dumps(rec), flush=True)
            target.unlink(missing_ok=True)
        for f in d.glob("t.*"):
            f.unlink()


if __name__ == "__main__":
    main()
