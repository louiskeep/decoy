"""Generated tables too large for memory are refused with exit 5 (GEN-STRICT C2, row 24k).

AT-C3: a `row_count` whose resident output cannot fit the machine is refused by `decoy validate`
and by `decoy run`'s pre-run gate, before any output file exists. The machine-memory reading is
patched so the result does not depend on the runner, and the engine call is patched to fail loudly
so a missed refusal never starts a five-billion-row run.

AT-C5: a capacity refusal raised by the engine during the run, and a bare `MemoryError`, both exit 5
with `error_kind: capacity`.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
import yaml
from decoy_engine import DecoyError
from decoy_engine.reasons.runtime import GENERATION_BUDGET_EXCEEDED
from typer.testing import CliRunner, Result

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_CAPACITY

runner = CliRunner()
_WIDE = {"COLUMNS": "10000"}
_CANARY = "canary7731"
_TABLE = "people"
_CODE = GENERATION_BUDGET_EXCEEDED
_HOST_BYTES = 8 * 1024**3
_HUGE_ROWS = 5_000_000_000


def _config(folder: Path, row_count: int) -> Path:
    columns = [
        {"name": "id", "type": "sequence", "start": 1},
        {"name": "tier", "type": "categorical", "categories": [f"{_CANARY}_a", f"{_CANARY}_b"]},
    ]
    cfg = {
        "version": 2,
        "global_settings": {"seed": 42},
        "tables": [{"name": _TABLE, "row_count": row_count, "generate_columns": columns}],
        "targets": {
            _TABLE: {"type": "file", "format": "csv", "path": str(folder / "out" / "people.csv")}
        },
    }
    path = folder / "gen.yaml"
    path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    return path


def _stderr(result: Result) -> str:
    try:
        return result.stderr
    except ValueError:
        return ""


def _no_canary(result: Result) -> None:
    for stream in (result.stdout, _stderr(result)):
        assert _CANARY not in stream.lower(), "a category value reached the output"
    assert "Traceback" not in result.output


@pytest.fixture
def eight_gib_host() -> Iterator[None]:
    with mock.patch(
        "decoy_engine.execution.out_of_core._budget.detect_effective_memory_bytes",
        return_value=_HOST_BYTES,
    ):
        yield


def _engine_must_not_run(*_args: Any, **_kwargs: Any) -> None:
    raise AssertionError("the run reached the engine; the gate should have refused it")


# --- AT-C3: validate and run refuse before anything is generated ------------------------------


@pytest.mark.usefixtures("eight_gib_host")
def test_at_c3_validate_exits_capacity(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["validate", str(_config(tmp_path, _HUGE_ROWS)), "--json"], env=_WIDE
    )
    assert result.exit_code == EXIT_CAPACITY, result.output
    hits = [m for m in json.loads(result.stdout)["messages"] if m["code"] == _CODE]
    assert hits and hits[0]["severity"] == "error", result.stdout
    text = hits[0]["message"]
    assert f"'{_TABLE}'" in text, text
    assert "row_count" in text, text
    assert "full-frame" not in text, text
    _no_canary(result)


@pytest.mark.usefixtures("eight_gib_host")
def test_at_c3_validate_human_output(tmp_path: Path) -> None:
    result = runner.invoke(app, ["validate", str(_config(tmp_path, _HUGE_ROWS))], env=_WIDE)
    assert result.exit_code == EXIT_CAPACITY, result.output
    text = " ".join(result.output.split())
    assert "resident generation needs at least" in text, text
    assert "full-frame" not in text, text
    _no_canary(result)


@pytest.mark.usefixtures("eight_gib_host")
@pytest.mark.parametrize("json_flag", [True, False], ids=["json", "human"])
def test_at_c3_run_stops_at_the_gate(tmp_path: Path, json_flag: bool) -> None:
    args = ["run", str(_config(tmp_path, _HUGE_ROWS))] + (["--json"] if json_flag else [])
    with mock.patch("decoy_engine.run_pipeline", side_effect=_engine_must_not_run) as engine:
        result = runner.invoke(app, args, env=_WIDE)
    assert result.exit_code == EXIT_CAPACITY, result.output
    assert not engine.called
    assert not (tmp_path / "out" / "people.csv").exists()
    if json_flag:
        payload = json.loads(result.stdout)
        assert payload["error_kind"] == "capacity", payload
        assert payload["code"] == _CODE, payload
    else:
        assert "capacity:" in result.output
    _no_canary(result)


# --- AT-C5: a capacity failure raised during the run ------------------------------------------


def _budget_exceeded() -> Exception:
    # The engine's budget exception is private; a public DecoyError carrying the registered
    # code takes the same exit path (the CLI keys on the code, not the class).
    err = DecoyError(
        f"[{_CODE}] resident generation needs at least 9 bytes (largest table '{_TABLE}'); "
        "8 bytes of memory are available."
    )
    err.code = _CODE  # type: ignore[attr-defined]
    return err


def test_at_c5_capacity_codes_name_the_generation_refusal() -> None:
    from decoy.cli.gate import capacity_codes

    assert _CODE in capacity_codes()


@pytest.mark.parametrize("json_flag", [True, False], ids=["json", "human"])
def test_at_c5_budget_exceeded_during_run_exits_capacity(tmp_path: Path, json_flag: bool) -> None:
    args = ["run", str(_config(tmp_path, 20))] + (["--json"] if json_flag else [])
    with mock.patch("decoy_engine.run_pipeline", side_effect=_budget_exceeded()):
        result = runner.invoke(app, args, env=_WIDE)
    assert result.exit_code == EXIT_CAPACITY, result.output
    if json_flag:
        payload = json.loads(result.stdout)
        assert payload["error_kind"] == "capacity", payload
        assert payload["code"] == _CODE, payload
    else:
        assert "capacity:" in result.output
    _no_canary(result)


@pytest.mark.parametrize("json_flag", [True, False], ids=["json", "human"])
def test_at_c5_bare_memory_error_exits_capacity_with_text(tmp_path: Path, json_flag: bool) -> None:
    args = ["run", str(_config(tmp_path, 20))] + (["--json"] if json_flag else [])
    with mock.patch("decoy_engine.run_pipeline", side_effect=MemoryError()):
        result = runner.invoke(app, args, env=_WIDE)
    assert result.exit_code == EXIT_CAPACITY, result.output
    if json_flag:
        payload = json.loads(result.stdout)
        assert payload["error_kind"] == "capacity", payload
        assert payload["error"].strip(), payload
    else:
        line = next(ln for ln in result.output.splitlines() if "capacity:" in ln)
        assert line.split("capacity:", 1)[1].strip(), result.output
    _no_canary(result)
