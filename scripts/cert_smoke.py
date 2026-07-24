#!/usr/bin/env python3
"""Standalone certification smoke test for the DP runtime environment.

Not a pytest test -- run it directly with the certified venv's interpreter:

    .venv-certified/bin/python scripts/cert_smoke.py

This is the proof that the pristine runtime install (engine 0.5.0 + decoy-cli
+ the pinned closure in requirements-certified.txt, no dev tooling) actually
reproduces certified row (platform, cpython 3.10.20, fingerprint
5a2f7ef7...). A real `fit_dp_snapshot` call only completes on a certified
row; everywhere else it raises `ProvenanceError(code="dp_stack_uncertified")`
(see tests/e2e/test_fit_command.py and tests/e2e/test_dp_provenance.py for
that refusal arm under the normal dev venv).

Exit code is 0 only if every assertion below holds; any failure exits
non-zero so this can gate a release the same way a pytest suite would.
"""

from __future__ import annotations

import sys

import pandas as pd


def _fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    from decoy_engine.quality import dp_provenance
    from decoy_engine.quality.dp import fit_dp_snapshot

    running_fingerprint = dp_provenance.compute_lock_fingerprint(
        dp_provenance.installed_distribution_set()
    )
    print("running platform:", dp_provenance.current_platform())
    print("running cpython:", dp_provenance.current_cpython())
    print("running fingerprint:", running_fingerprint)

    # -- (a) the real fit, on the certified stack, must complete -----------
    df = pd.DataFrame(
        {
            "amount": [10.5, 22.1, 9.9, 100.0, 55.2, 31.4, 18.8, 42.0] * 25,
            "is_active": [True, False, True, True, False, True, False, False] * 25,
        }
    )
    column_schema = {
        "amount": {"kind": "numeric", "carrier": "number", "bounds": [0.0, 150.0]},
        "is_active": {"kind": "categorical", "carrier": "flag"},
    }
    artifact = fit_dp_snapshot(df, column_schema, epsilon=8.0, delta=1e-5)
    dp_block = artifact["dp"]

    if dp_block["schema"] != "dps-marginal/v3":
        _fail(f"expected dp schema 'dps-marginal/v3', got {dp_block['schema']!r}")
    print("dp schema:", dp_block["schema"])

    recorded_fingerprint = dp_block["provenance"]["fingerprint"]
    if recorded_fingerprint != running_fingerprint:
        _fail(
            f"recorded provenance fingerprint {recorded_fingerprint!r} does not "
            f"match the running environment's {running_fingerprint!r}"
        )
    print("recorded fingerprint matches running environment: OK")
    print("FIT + ARTIFACT: OK")

    # -- (b) downstream: does generation consume a dps-marginal/v3 snapshot? --
    # decoy_engine.plan._generation.read_and_pin_snapshots reads every
    # `type: statistical` generate column's snapshot_file at compile time and
    # embeds it into the compiled Plan; decoy_engine.generation.synthesize.
    # generate_tables then samples from that pinned snapshot alone (see
    # engine tests/unit/generation/test_generate_dp_contract.py, e.g.
    # TestConsumeOnlyContract). That path is wired, so this script exercises
    # it for real rather than asserting fit-only.
    import json
    import tempfile
    from datetime import datetime, timezone
    from pathlib import Path

    from decoy_engine.plan import compile_plan
    from decoy_engine.profile import Profile

    with tempfile.TemporaryDirectory() as tmp:
        snapshot_path = Path(tmp) / "dp_snapshot.json"
        snapshot_path.write_text(json.dumps(artifact), encoding="utf-8")

        config = {
            "global_settings": {"seed": 1, "dp": {"epsilon": 8.0, "delta": 1e-5}},
            "tables": [
                {
                    "name": "customers",
                    "row_count": 10,
                    "generate_columns": [
                        {
                            "name": "amount",
                            "type": "statistical",
                            "snapshot_file": str(snapshot_path),
                        },
                        {
                            "name": "is_active",
                            "type": "statistical",
                            "snapshot_file": str(snapshot_path),
                        },
                    ],
                }
            ],
        }
        profile = Profile(
            schema_version=1,
            tables=(),
            relationships=(),
            profiled_at=datetime.now(timezone.utc),
            decoy_engine_version="cert-smoke",
        )
        plan = compile_plan(config, profile, decoy_engine_version="cert-smoke")

        from decoy_engine.generation.synthesize import generate_tables

        out = generate_tables(plan)
        amounts = out["customers"]["amount"].to_pylist()
        flags = out["customers"]["is_active"].to_pylist()

    if len(amounts) != 10 or len(flags) != 10:
        _fail(f"expected 10 generated rows, got {len(amounts)} amounts / {len(flags)} flags")
    if not all(isinstance(v, bool) for v in flags):
        _fail(f"expected bool values for is_active, got {[type(v) for v in flags]}")
    print("generated amounts:", amounts)
    print("generated is_active:", flags)
    print("GENERATION FROM DP SNAPSHOT: OK")

    print("CERTIFICATION SMOKE PASSED")


if __name__ == "__main__":
    main()
