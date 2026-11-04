"""Fail when a registered sentry baseline grows, is re-homed, or carries a weak reason.

Usage: ratchet_check.py [--root DIR] [--base REF] [--slice NAME]
  --base   default: merge-base of origin/main and HEAD
  --slice  a newly registered baseline's created_in must equal NAME
The logic lives in tests/sentry/_ratchet.py so the unit tests and this gate step share it.
Exit 0 clean, 1 on a finding, 2 when there is no merge base.
"""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path


def _load():
    # Loaded by path: tests/sentry is not a package, and the checked tree may be a scratch repo.
    path = Path(__file__).resolve().parents[2] / "tests" / "sentry" / "_ratchet.py"
    spec = importlib.util.spec_from_file_location("_ratchet", path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_ratchet"] = mod
    spec.loader.exec_module(mod)
    return mod


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    ap.add_argument("--base")
    ap.add_argument("--slice", dest="slice_name")
    args = ap.parse_args(argv)
    base = args.base
    if not base:
        res = subprocess.run(
            ["git", "-C", str(args.root), "merge-base", "origin/main", "HEAD"],
            capture_output=True,
            text=True,
        )
        if res.returncode != 0:
            print("ratchet: no merge base; run: git fetch origin main", file=sys.stderr)
            return 2
        base = res.stdout.strip()
    findings, report = _load().check(args.root, base, args.slice_name)
    for line in report:
        print(f"ratchet: {line}")
    for line in findings:
        print(f"ratchet: FAIL {line}", file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
