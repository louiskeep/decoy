"""SUB-RUN C1: `decoy run` applies a pipeline's `subset:` block through the engine.

AT-C1 `run` with `subset:` writes only the subset rows; `--json` has a `subset` object with counts
and the human summary has one "subset: kept N of M rows across K tables" line.
AT-C2 `--chunked` with `subset:` exits 1 with `config.subset_run_unsupported`.
AT-C3 `--no-subset` passes `subset_request="skip"` and the output says `{"applied": false}`.
AT-C4 a subset failure keeps `run`'s generic handling: exit 3 and the reason code shown.
AT-C5 `validate` and `validate compile --explain` compile the run config, so a subset pipeline
passes, and a subset config error is a finding, not a crash.

Mutations: strip `subset` from the config in the CLI (AT-C3 `test_no_subset_sends_skip_and_leaves_
the_config_alone` and the sentry in `tests/sentry/run/test_no_subset_edit.py` go red); special-case
`SubsetError` in `run/` (the sentry goes red); compile `raw` instead of the split run config in
`_run_compile_layer` or `compile` (AT-C5 `test_gate_and_compile_accept_a_subset_pipeline` goes red).
"""

from __future__ import annotations

import json as _json
from pathlib import Path
from typing import Any

import polars as pl
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from tests.keyed_secret import TEST_MASK_SECRET_REF

pytestmark = pytest.mark.usefixtures("mask_secret")

runner = CliRunner()

CUSTOMERS = 20
ORDERS = 40


def _config(tmp_path: Path, *, budget: dict | None = None) -> Path:
    """customers (20) and orders (40, FK to customers), parquet in and out, sample 25% of customers."""
    pl.DataFrame({"id": list(range(1, CUSTOMERS + 1))}).write_parquet(
        tmp_path / "customers.parquet"
    )
    pl.DataFrame(
        {
            "id": list(range(1, ORDERS + 1)),
            "customer_id": [(i % CUSTOMERS) + 1 for i in range(ORDERS)],
        }
    ).write_parquet(tmp_path / "orders.parquet")
    subset: dict[str, Any] = {
        "seeds": [{"table": "customers", "mode": "sample", "key_columns": ["id"], "fraction": 0.25}]
    }
    if budget is not None:
        subset["budget"] = budget
    config = {
        "version": 2,
        "global_settings": {"seed": 7, "mask_secret_ref": TEST_MASK_SECRET_REF},
        "sources": {
            name: {"type": "file", "format": "parquet", "path": str(tmp_path / f"{name}.parquet")}
            for name in ("customers", "orders")
        },
        "tables": [
            {
                "name": "customers",
                "columns": [{"name": "id", "strategy": "hash", "namespace": "customer_identity"}],
            },
            {
                "name": "orders",
                "columns": [
                    {"name": "id", "strategy": "passthrough"},
                    {"name": "customer_id", "strategy": "hash", "namespace": "customer_identity"},
                ],
            },
        ],
        "relationships": [
            {
                "parent": {"table": "customers", "columns": ["id"]},
                "children": [{"table": "orders", "columns": ["customer_id"]}],
                "orphan_policy": "preserve",
                "namespace": "customer_identity",
            }
        ],
        "subset": subset,
        "targets": {
            name: {
                "type": "file",
                "format": "parquet",
                "path": str(tmp_path / f"out_{name}.parquet"),
            }
            for name in ("customers", "orders")
        },
    }
    path = tmp_path / "pipeline.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def _out_rows(tmp_path: Path, name: str) -> int:
    return pl.read_parquet(tmp_path / f"out_{name}.parquet").height


def test_subset_run_writes_only_the_subset_rows(tmp_path: Path) -> None:
    """AT-C1 (`--json`): the counts in `subset` are the rows on disk."""
    path = _config(tmp_path)
    result = runner.invoke(app, ["run", str(path), "--json"])
    assert result.exit_code == 0, result.output
    subset = _json.loads(result.stdout)["subset"]
    assert subset["applied"] is True
    assert set(subset["tables"]) == {"customers", "orders"}
    for name, source in (("customers", CUSTOMERS), ("orders", ORDERS)):
        counts = subset["tables"][name]
        assert counts["source_rows"] == source
        assert counts["kept_rows"] == _out_rows(tmp_path, name)
    assert 0 < subset["tables"]["customers"]["kept_rows"] < CUSTOMERS
    assert subset["tables"]["orders"]["kept_rows"] < ORDERS


def test_subset_run_prints_one_summary_line(tmp_path: Path) -> None:
    """AT-C1 (human): `subset: kept N of M rows across K tables`, N and M summed over tables."""
    path = _config(tmp_path)
    result = runner.invoke(app, ["run", str(path)])
    assert result.exit_code == 0, result.output
    kept = _out_rows(tmp_path, "customers") + _out_rows(tmp_path, "orders")
    line = f"subset: kept {kept} of {CUSTOMERS + ORDERS} rows across 2 tables"
    assert result.output.count("subset: kept") == 1
    assert line in result.output


def test_chunked_with_subset_exits_1_with_the_engine_code(tmp_path: Path) -> None:
    """AT-C2: refused before any read, nothing written."""
    from decoy_engine import reasons

    path = _config(tmp_path)
    result = runner.invoke(app, ["run", str(path), "--chunked", "--json"])
    assert result.exit_code == 1, result.output
    payload = _json.loads(result.stdout)
    assert payload["reason"]["code"] == reasons.config.SUBSET_RUN_UNSUPPORTED
    assert not (tmp_path / "out_customers.parquet").exists()


def test_chunked_with_subset_is_refused_under_no_subset_too(tmp_path: Path) -> None:
    """AT-C2: the CLI never strips the block, so `--no-subset` does not make `--chunked` legal."""
    path = _config(tmp_path)
    result = runner.invoke(app, ["run", str(path), "--chunked", "--no-subset"])
    assert result.exit_code == 1, result.output
    assert not (tmp_path / "out_customers.parquet").exists()


def test_no_subset_sends_skip_and_leaves_the_config_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AT-C3: `subset_request="skip"` reaches the engine with the config's `subset` untouched,
    and the full sources are masked."""
    import decoy_engine

    path = _config(tmp_path)
    seen: dict[str, Any] = {}
    real = decoy_engine.run_pipeline

    def spy(config: dict, *args: Any, **kwargs: Any) -> Any:
        seen["request"] = kwargs.get("subset_request")
        seen["subset"] = config.get("subset")
        return real(config, *args, **kwargs)

    monkeypatch.setattr(decoy_engine, "run_pipeline", spy)
    result = runner.invoke(app, ["run", str(path), "--json", "--no-subset"])
    assert result.exit_code == 0, result.output
    assert seen["request"] == "skip"
    assert seen["subset"] is not None
    # The engine gets the validated block with its defaults filled in, seeds as written.
    assert [seed["table"] for seed in seen["subset"]["seeds"]] == ["customers"]
    assert _json.loads(result.stdout)["subset"] == {"applied": False}
    assert _out_rows(tmp_path, "customers") == CUSTOMERS
    assert _out_rows(tmp_path, "orders") == ORDERS


def test_default_run_sends_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AT-C3: without the flag the engine is asked to apply the config's block."""
    import decoy_engine

    path = _config(tmp_path)
    seen: list[Any] = []
    real = decoy_engine.run_pipeline

    def spy(config: dict, *args: Any, **kwargs: Any) -> Any:
        seen.append(kwargs.get("subset_request"))
        return real(config, *args, **kwargs)

    monkeypatch.setattr(decoy_engine, "run_pipeline", spy)
    assert runner.invoke(app, ["run", str(path), "--json"]).exit_code == 0
    assert seen == ["config"]


def test_no_subset_human_output_says_not_applied(tmp_path: Path) -> None:
    """The help text promises the summary reports `applied false`."""
    result = runner.invoke(app, ["run", str(_config(tmp_path)), "--no-subset"])
    assert result.exit_code == 0, result.output
    assert "subset: not applied (--no-subset)" in result.output
    assert "subset: kept" not in result.output


def test_a_subset_budget_failure_keeps_the_generic_run_exit(tmp_path: Path) -> None:
    """AT-C4: a `SubsetError` is a run failure like any other: exit 3, the code shown, no
    special case in `run/`."""
    from decoy_engine import reasons

    path = _config(tmp_path, budget={"max_total_rows": 1})
    result = runner.invoke(app, ["run", str(path), "--json"])
    assert result.exit_code == 3, result.output
    payload = _json.loads(result.stdout)
    assert payload["status"] == "error"
    assert payload["reason"]["code"] == reasons.subset.SUBSET_BUDGET_EXCEEDED
    assert not (tmp_path / "out_customers.parquet").exists()


def test_gate_and_compile_accept_a_subset_pipeline(tmp_path: Path) -> None:
    """AT-C5: both compile the run config, so a valid `subset:` is not a compile error."""
    path = _config(tmp_path)
    validated = runner.invoke(app, ["validate", str(path), "--json"])
    assert validated.exit_code == 0, validated.output
    compiled = runner.invoke(app, ["validate", "compile", str(path), "--explain"])
    assert compiled.exit_code == 0, compiled.output


def _edit(path: Path, change) -> None:
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(cfg)
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")


def _no_orphan_policy(cfg: dict) -> None:
    del cfg["relationships"][0]["orphan_policy"]


def _subset_is_a_list(cfg: dict) -> None:
    cfg["subset"] = [{"table": "customers"}]


@pytest.mark.parametrize("change", [_no_orphan_policy, _subset_is_a_list])
def test_a_malformed_subset_config_is_a_schema_error_not_a_traceback(
    tmp_path: Path, change
) -> None:
    """AT-C5: the split reads a validated dump, so `validate compile --explain` and `validate`
    show the schema error. Neither prints a raw KeyError or AttributeError."""
    path = _config(tmp_path)
    _edit(path, change)
    compiled = runner.invoke(app, ["validate", "compile", str(path), "--explain"])
    assert compiled.exit_code == 1, compiled.output
    validated = runner.invoke(app, ["validate", str(path), "--json"])
    assert validated.exit_code == 1, validated.output
    for result in (compiled, validated):
        assert result.exception is None or isinstance(result.exception, SystemExit)
        for text in ("KeyError", "AttributeError", "Traceback", "object has no attribute"):
            assert text not in result.output


def test_a_composite_length_mismatch_with_subset_is_the_engines_subset_error(
    tmp_path: Path,
) -> None:
    """AT-C5, real trigger: with a profile the empty-profile builder is skipped, so the split is
    what finds the mismatch. The engine's code is shown and nothing crashes."""
    from datetime import datetime

    from decoy_engine import reasons
    from decoy_engine.profile import Profile, profile_to_json

    path = _config(tmp_path)
    _edit(path, lambda cfg: cfg["relationships"][0]["parent"].update(columns=["id", "id"]))
    profile = tmp_path / "profile.json"
    profile.write_text(
        profile_to_json(
            Profile(
                schema_version=1,
                tables=(),
                relationships=(),
                profiled_at=datetime(1970, 1, 1),
                decoy_engine_version="0",
                profile_seed=None,
            )
        ),
        encoding="utf-8",
    )
    result = runner.invoke(
        app, ["validate", "compile", str(path), "--explain", "--profile", str(profile)]
    )
    assert result.exit_code == 1, result.output
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert reasons.subset.SUBSET_RELATIONSHIP_COMPOSITE_LENGTH in result.output


def test_the_gate_turns_a_subset_error_into_a_finding_defensive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AT-C5, injected: no real input reaches the gate's `SubsetError` handler once the config
    layer has validated the block, so the engine's split is made to raise. The handler stays
    as a defence; this cell proves it reports a finding and does not crash."""
    import decoy_engine.subset as engine_subset
    from decoy_engine import reasons
    from decoy_engine.subset import SubsetConfigError

    def boom(config: dict) -> Any:
        raise SubsetConfigError(
            code=reasons.subset.SUBSET_UNKNOWN_TABLE, message="subset table unknown"
        )

    monkeypatch.setattr(engine_subset, "split_subset_config", boom)
    result = runner.invoke(app, ["validate", str(_config(tmp_path)), "--json"])
    assert result.exit_code == 1, result.output
    assert result.exception is None or isinstance(result.exception, SystemExit)
    codes = [m["code"] for m in _json.loads(result.stdout)["messages"]]
    assert reasons.subset.SUBSET_UNKNOWN_TABLE in codes


def test_no_subset_over_the_capacity_limit_exits_5(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--no-subset` reads every row, so the gate prices the full run and refuses it. Without
    the split the estimate reports "not applicable: subset" and the refusal is skipped."""
    from tests.e2e.test_run_preflight_capacity_parity import _fanin_config

    monkeypatch.setattr(
        "decoy_engine.execution.out_of_core._budget.detect_effective_memory_bytes",
        lambda *a, **k: 1024 * 1024,
    )
    path = _fanin_config(tmp_path)
    _edit(
        path,
        lambda cfg: cfg.update(
            subset={
                "seeds": [
                    {"table": "parent_0", "mode": "sample", "key_columns": ["id"], "fraction": 0.5}
                ]
            }
        ),
    )
    result = runner.invoke(app, ["run", str(path), "--no-subset", "--json"])
    assert result.exit_code == 5, result.output
    assert _json.loads(result.stdout)["error_kind"] == "capacity"
