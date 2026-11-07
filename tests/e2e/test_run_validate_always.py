"""VALIDATE-ALWAYS P2: `decoy run` runs the whole `decoy validate` gate before it reads data.

The parity matrix feeds one broken config per finding kind to `decoy validate` and `decoy run`
(plain and `--chunked`) and asserts the same exit code and first code, a `--json` refusal
envelope that carries the validate `messages`, and zero calls to the readers and the engine.
The other cells pin the plan's acceptance tests AT-1 to AT-14 (docs/plans/2026-11-06-validate-always.md).
"""

from __future__ import annotations

import json as _json
import re
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest import mock

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_CAPACITY, EXIT_OK, EXIT_RUNTIME, EXIT_USAGE, EXIT_WARNINGS
from decoy.cli.gate import (
    ERROR_TEXT_CAP,
    GateRoute,
    PreRunCheckError,
    check_before_run,
    run_gate,
)
from decoy.ui.output import OutputMode
from tests.e2e.test_run_preflight_capacity_parity import _fanin_config
from tests.keyed_secret import TEST_MASK_SECRET_REF

pytestmark = pytest.mark.usefixtures("mask_secret")

runner = CliRunner()
MARKER = "runmarker5e17a9"


# -- fixtures -----------------------------------------------------------------------------------


def _cfg(tmp_path: Path, **over: Any) -> dict[str, Any]:
    """A valid one-table redact job: the source CSV exists, nothing else is wrong."""
    src = tmp_path / "in.csv"
    pd.DataFrame({"email": ["a@b.com", "c@d.com"], "id": [1, 2]}).to_csv(src, index=False)
    cfg: dict[str, Any] = {
        "version": 2,
        "global_settings": {"seed": 42},
        "sources": {"customers": {"type": "file", "format": "csv", "path": str(src)}},
        "tables": [{"name": "customers", "columns": [{"name": "email", "strategy": "redact"}]}],
        "targets": {
            "customers": {"type": "file", "format": "csv", "path": str(tmp_path / "out.csv")}
        },
    }
    cfg.update(over)
    return cfg


def _write(tmp_path: Path, cfg: dict[str, Any] | str, name: str = "pipeline.yaml") -> Path:
    p = tmp_path / name
    p.write_text(cfg if isinstance(cfg, str) else yaml.safe_dump(cfg), encoding="utf-8")
    return p


@pytest.fixture()
def spies(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every call into a reader or the engine; none may happen on a refusal."""
    calls: list[str] = []

    def _spy(name: str) -> Callable[..., Any]:
        def _called(*_a: Any, **_k: Any) -> Any:
            calls.append(name)
            raise RuntimeError(f"{name} was called")

        return _called

    monkeypatch.setattr("decoy.cli.run.read_source", _spy("read_source"))
    monkeypatch.setattr("decoy.cli.run.iter_source_chunks", _spy("iter_source_chunks"))
    monkeypatch.setattr("decoy_engine.run_pipeline", _spy("run_pipeline"))
    monkeypatch.setattr("decoy_engine.run_mask_pipeline_chunked", _spy("run_mask_pipeline_chunked"))
    return calls


def _plan_error(code: str, message: str = "forced") -> Any:
    from decoy_engine.plan import PlanCompileError

    return PlanCompileError(code, "tables.customers", message)


# -- parity matrix: one broken config per finding kind ---------------------------------------


def _yaml_syntax(tmp_path: Path, mp: pytest.MonkeyPatch) -> Path:
    return _write(tmp_path, "a: [unclosed\n")


def _yaml_empty(tmp_path: Path, mp: pytest.MonkeyPatch) -> Path:
    return _write(tmp_path, "")


def _yaml_list(tmp_path: Path, mp: pytest.MonkeyPatch) -> Path:
    return _write(tmp_path, "- a\n- b\n")


def _schema(tmp_path: Path, mp: pytest.MonkeyPatch) -> Path:
    cfg = _cfg(tmp_path)
    del cfg["version"]
    return _write(tmp_path, cfg)


def _config_only(tmp_path: Path, mp: pytest.MonkeyPatch) -> Path:
    def boom(*_a: Any, **_k: Any) -> Any:
        raise _plan_error("synthetic_config_check")

    mp.setattr("decoy_engine.run_config_only_checks", boom)
    return _write(tmp_path, _cfg(tmp_path))


def _ner_absent(tmp_path: Path, mp: pytest.MonkeyPatch) -> Path:
    def boom(*_a: Any, **_k: Any) -> Any:
        raise _plan_error("ner_spacy_not_installed")

    mp.setattr("decoy_engine.run_config_only_checks", boom)
    return _write(tmp_path, _cfg(tmp_path))


def _compile_error(tmp_path: Path, mp: pytest.MonkeyPatch) -> Path:
    def boom(*_a: Any, **_k: Any) -> Any:
        raise _plan_error("synthetic_compile_failure")

    mp.setattr("decoy_engine.plan.compile_plan", boom)
    return _write(tmp_path, _cfg(tmp_path))


def _missing_source(tmp_path: Path, mp: pytest.MonkeyPatch) -> Path:
    cfg = _cfg(tmp_path)
    cfg["sources"]["customers"]["path"] = str(tmp_path / "ABSENT.csv")
    return _write(tmp_path, cfg)


def _unreadable_source(tmp_path: Path, mp: pytest.MonkeyPatch) -> Path:
    mp.setattr("decoy_engine.profile.profile_source", mock.Mock(side_effect=ValueError(MARKER)))
    return _write(tmp_path, _cfg(tmp_path))


def _fan_in(tmp_path: Path, mp: pytest.MonkeyPatch) -> Path:
    mp.setattr(
        "decoy_engine.execution.out_of_core._budget.detect_effective_memory_bytes",
        lambda *a, **k: 1024 * 1024,
    )
    return _fanin_config(tmp_path)


# (cell id, builder, exit code, first code)
_MATRIX: list[tuple[str, Callable[[Path, pytest.MonkeyPatch], Path], int, str | None]] = [
    ("yaml_syntax", _yaml_syntax, EXIT_USAGE, "yaml.parse_error"),
    ("yaml_empty", _yaml_empty, EXIT_USAGE, "yaml.empty"),
    ("yaml_list", _yaml_list, EXIT_USAGE, "yaml.not_mapping"),
    ("schema", _schema, EXIT_USAGE, None),
    ("config_only", _config_only, EXIT_USAGE, "synthetic_config_check"),
    ("ner_absent", _ner_absent, EXIT_USAGE, "missing_extra"),
    ("compile_error", _compile_error, EXIT_USAGE, "synthetic_compile_failure"),
    ("missing_source", _missing_source, EXIT_USAGE, "source.customers.exists"),
    ("unreadable_source", _unreadable_source, EXIT_USAGE, "capacity_source_unprofilable"),
    ("fan_in", _fan_in, EXIT_CAPACITY, "out_of_core_fanin_exceeds_budget"),
]


def _cap(text: str) -> str:
    return text[:ERROR_TEXT_CAP] + "..." if len(text) > ERROR_TEXT_CAP else text


@pytest.mark.parametrize("flags", [(), ("--chunked",)], ids=["plain", "chunked"])
@pytest.mark.parametrize(
    ("cell", "build", "exit_code", "code"), _MATRIX, ids=[m[0] for m in _MATRIX]
)
def test_run_refuses_what_validate_refuses_before_any_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    spies: list[str],
    cell: str,
    build: Callable[[Path, pytest.MonkeyPatch], Path],
    exit_code: int,
    code: str | None,
    flags: tuple[str, ...],
) -> None:
    """AT-1, AT-2, AT-3, AT-5, AT-5e, AT-5y, AT-9. Mutations: delete the `check_before_run` call
    (no refusal, red); move it below `_load_sources_from_config` (spy sees a read, red); map a
    capacity refusal to 1 (fan_in cell); emit `messages` only for config failures (AT-5)."""
    path = build(tmp_path, monkeypatch)
    validated = runner.invoke(app, ["validate", str(path), "--json"])
    vpayload = _json.loads(validated.stdout)
    result = runner.invoke(app, ["run", str(path), "--json", *flags])
    payload = _json.loads(result.stdout)

    if cell == "fan_in" and flags:
        # AT-3c: on --chunked the capacity refusal is advisory; the gate lets the job on.
        assert result.exit_code != EXIT_CAPACITY, result.output
        return

    first_code = vpayload["messages"][0]["code"]
    assert code is None or first_code == code
    assert validated.exit_code == result.exit_code == exit_code, result.output
    assert spies == []
    assert set(payload) >= {
        "command",
        "status",
        "config",
        "mode",
        "error",
        "error_kind",
        "messages",
    }
    assert payload["status"] == "error"
    assert payload["messages"] == [
        {**m, "message": _cap(m["message"])} for m in vpayload["messages"]
    ]
    assert payload["messages"][0]["code"] == first_code
    if cell == "fan_in":
        assert payload["error_kind"] == "capacity"
        assert payload["code"] == code
    elif cell == "ner_absent":
        assert payload["error_kind"] == "missing_extra"
        assert payload["extra"] == "ner"
    else:
        assert payload["error_kind"] == "validation"
    assert not (tmp_path / "out.csv").exists()


def test_missing_source_stderr_names_the_location_and_writes_nothing(
    tmp_path: Path, spies: list[str]
) -> None:
    """AT-1. Mutation: run the gate after the read."""
    path = _missing_source(tmp_path, pytest.MonkeyPatch())
    result = runner.invoke(app, ["run", str(path)])
    assert result.exit_code == EXIT_USAGE
    assert "sources.customers.path" in "".join(result.stderr.split())
    assert spies == []
    assert not (tmp_path / "out.csv").exists()


# -- AT-3c: chunked capacity ----------------------------------------------------------------------


def _remap(path: Path) -> None:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    for rel in data["relationships"]:
        rel["orphan_policy"] = "remap"
    for table in data["tables"]:  # chunked FK masking needs declared, matching key dtypes
        for column in table["columns"]:
            column["dtype"] = "string"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")


def test_chunked_capacity_refusal_is_a_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AT-3c. The `remap` fan-in graph is not refused by the gate on --chunked and runs to exit 0; the `preserve` graph is refused by the chunked compatibility rule (exit 1).
    Mutation: drop the route rule, and the remap variant exits 5."""
    path = _fan_in(tmp_path, monkeypatch)
    plain = runner.invoke(app, ["run", str(path), "--json"])
    assert plain.exit_code == EXIT_CAPACITY
    preserve = runner.invoke(app, ["run", str(path), "--chunked"])
    assert preserve.exit_code == EXIT_USAGE
    assert "chunked_fk_orphan_policy_not_remap" in preserve.output
    _remap(path)
    remap = runner.invoke(app, ["run", str(path), "--chunked"])
    assert remap.exit_code == EXIT_OK, remap.output
    assert (tmp_path / "child.out.parquet").exists()


def test_chunked_gate_warning_text_names_the_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """L2: the demoted finding says it is advisory on --chunked, not 'use a larger tier'."""
    path = _fan_in(tmp_path, monkeypatch)
    from decoy.cli.gate import run_gate_on_config

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    result = run_gate_on_config(raw, path, GateRoute.CHUNKED)
    capacity = [f for f in result.findings if f.code == "out_of_core_fanin_exceeds_budget"]
    assert capacity and capacity[0].severity == "warning"
    assert "--chunked" in capacity[0].message and not result.capacity_insufficient


# -- AT-4: unique column ------------------------------------------------------------------------


def _unique_cfg(tmp_path: Path) -> Path:
    cfg = _cfg(tmp_path)
    cfg["tables"][0]["columns"] = [
        {
            "name": "email",
            "strategy": "faker",
            "provider": "person_email",
            "cardinality_mode": "unique",
        }
    ]
    return _write(tmp_path, cfg)


def test_unique_column_runs_and_validate_warns(tmp_path: Path) -> None:
    """AT-4. Mutation: restore the error severity for `compile.needs_profile`."""
    path = _unique_cfg(tmp_path)
    assert runner.invoke(app, ["run", str(path)]).exit_code == EXIT_OK
    assert (tmp_path / "out.csv").exists()
    validated = runner.invoke(app, ["validate", str(path), "--json"])
    assert validated.exit_code == EXIT_OK
    assert "compile.needs_profile" in [m["code"] for m in _json.loads(validated.stdout)["messages"]]
    assert (
        runner.invoke(app, ["validate", str(path), "--fail-on-warning"]).exit_code == EXIT_WARNINGS
    )
    narrow = runner.invoke(app, ["validate", "compile", str(path), "--no-profile"])
    assert narrow.exit_code == EXIT_USAGE


# -- AT-6: warnings ----------------------------------------------------------------------------


def test_warnings_print_one_count_line_in_human_mode_only(tmp_path: Path) -> None:
    """AT-6. Mutation: print each warning to stdout."""
    path = _write(tmp_path, _cfg(tmp_path))
    (tmp_path / "out.csv").write_text("old\n", encoding="utf-8")
    human = runner.invoke(app, ["run", str(path)])
    assert human.exit_code == EXIT_OK, human.output
    assert len(re.findall(r"pre-run warning", human.stderr)) == 1
    assert "pre-run warning" not in human.stdout
    as_json = runner.invoke(app, ["run", str(path), "--json"])
    assert as_json.exit_code == EXIT_OK
    _json.loads(as_json.stdout)
    assert "pre-run warning" not in as_json.stderr
    quiet = runner.invoke(app, ["run", str(path), "--quiet"])
    assert quiet.exit_code == EXIT_OK
    assert quiet.stdout == "" and "pre-run warning" not in quiet.stderr


# -- AT-7: secrets ------------------------------------------------------------------------------


def test_bad_mask_secret_ref_stays_behind_the_de02_guard(tmp_path: Path) -> None:
    """AT-7. Mutation: move the gate above the DE-02 guard (the message changes, red)."""
    cfg = _cfg(tmp_path)
    cfg["global_settings"]["mask_secret_ref"] = [MARKER]
    result = runner.invoke(app, ["run", str(_write(tmp_path, cfg)), "--json"])
    assert result.exit_code == EXIT_USAGE
    assert MARKER not in result.stdout + result.stderr
    assert "Invalid global_settings.mask_secret_ref" in result.stdout


def test_keyed_config_passes_the_gate_with_only_the_flag(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    cfg["tables"][0]["columns"] = [{"name": "email", "strategy": "hash", "namespace": "n"}]
    result = runner.invoke(
        app, ["run", str(_write(tmp_path, cfg)), "--mask-secret", TEST_MASK_SECRET_REF]
    )
    assert result.exit_code == EXIT_OK, result.output


# -- AT-7m: reader text and the message cap -----------------------------------------------------


@pytest.mark.parametrize("argv", [["run"], ["run", "--json"], ["validate", "--json"]])
def test_reader_text_never_reaches_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, argv: list[str]
) -> None:
    """AT-7m. The reader's own error carries the marker; the engine wraps it into its message;
    the finding must not. Mutation: restore the engine message in `_check_capacity`."""
    path = _unreadable_source(tmp_path, monkeypatch)
    result = runner.invoke(app, [argv[0], str(path), *argv[1:]])
    assert result.exit_code == EXIT_USAGE
    assert MARKER not in result.stdout + result.stderr
    if "--json" in argv:
        codes = [m["code"] for m in _json.loads(result.stdout)["messages"]]
        assert "capacity_source_unprofilable" in codes


def test_run_caps_each_message_and_validate_does_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AT-7m cap. Mutation: drop the run-envelope cap."""
    monkeypatch.setattr(
        "decoy_engine.run_config_only_checks",
        mock.Mock(side_effect=_plan_error("synthetic_long", "m" * 600)),
    )
    path = _write(tmp_path, _cfg(tmp_path))
    ran = _json.loads(runner.invoke(app, ["run", str(path), "--json"]).stdout)
    assert len(ran["messages"][0]["message"]) == ERROR_TEXT_CAP + 3
    assert ran["messages"][0]["message"].endswith("...")
    assert len(ran["error"]) <= ERROR_TEXT_CAP + 3
    validated = _json.loads(runner.invoke(app, ["validate", str(path), "--json"]).stdout)
    assert len(validated["messages"][0]["message"]) == 600


# -- AT-8: duckdb -------------------------------------------------------------------------------


def _duckdb_cfg(tmp_path: Path) -> tuple[Path, Path]:
    import duckdb

    db = tmp_path / "in.duckdb"
    con = duckdb.connect(str(db))
    try:
        con.execute("CREATE TABLE customers AS SELECT 'a@b.com' AS email")
    finally:
        con.close()
    cfg = _cfg(tmp_path)
    cfg["sources"] = {}
    return _write(tmp_path, cfg), db


def test_gate_runs_on_the_staged_parquet(tmp_path: Path) -> None:
    """AT-8. Mutation: run the gate on the YAML before staging (no source declared, red)."""
    path, db = _duckdb_cfg(tmp_path)
    result = runner.invoke(app, ["run", str(path), "--duckdb-source", f"customers={db}"])
    assert result.exit_code == EXIT_OK, result.output


def test_gate_refusal_removes_the_staging_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, db = _duckdb_cfg(tmp_path)
    made: list[str] = []
    real = tempfile.mkdtemp

    def _record(*a: Any, **k: Any) -> str:
        d = real(*a, **k)
        made.append(d)
        return d

    monkeypatch.setattr(tempfile, "mkdtemp", _record)
    monkeypatch.setattr(
        "decoy_engine.plan.compile_plan", mock.Mock(side_effect=_plan_error("synthetic_compile"))
    )
    result = runner.invoke(app, ["run", str(path), "--duckdb-source", f"customers={db}"])
    assert result.exit_code == EXIT_USAGE
    assert made and not any(Path(d).exists() for d in made)


# -- AT-10: notify, AT-12: chain, AT-13: dialect, AT-14: runtime ---------------------------------


def test_gate_refusal_sends_one_failure_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AT-10. Mutation: raise `typer.Exit` from the adapter (no event)."""
    path = _missing_source(tmp_path, monkeypatch)
    with mock.patch("decoy.notify.send_webhook", return_value=(True, None)) as spy:
        result = runner.invoke(
            app, ["run", str(path), "--notify", "webhook:https://hooks.example.com/x", "--json"]
        )
    assert result.exit_code == EXIT_USAGE
    assert spy.call_count == 1
    assert "PreRunCheckError" in str(spy.call_args)
    assert MARKER not in str(spy.call_args)


def test_pre_run_check_error_has_no_cause_or_context(tmp_path: Path) -> None:
    """AT-12. Mutation: build the error inside an `except` block."""
    path = _missing_source(tmp_path, pytest.MonkeyPatch())
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    state = mock.Mock(mode=OutputMode.default)
    with pytest.raises(PreRunCheckError) as caught:
        check_before_run(raw, path, GateRoute.PLAIN, state)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert caught.value.exit_code == EXIT_USAGE
    result = run_gate(path)
    refusal = PreRunCheckError.from_findings(result.findings, str(path))
    assert refusal.__cause__ is None and refusal.__context__ is None


def test_headerless_dialect_csv_passes_validate_and_run(tmp_path: Path) -> None:
    """AT-13. Mutation: make the gate bypass the engine reader `profile_source` uses."""
    src = tmp_path / "in.psv"
    src.write_text("1|alice|31\n2|bob|4\n", encoding="utf-8")
    cfg = _cfg(tmp_path)
    cfg["sources"]["customers"] = {
        "type": "file",
        "format": "csv",
        "path": str(src),
        "has_header": False,
        "column_names": ["id", "email", "age"],
        "delimiter": "|",
    }
    path = _write(tmp_path, cfg)
    assert runner.invoke(app, ["validate", str(path)]).exit_code == EXIT_OK
    assert runner.invoke(app, ["run", str(path)]).exit_code == EXIT_OK


def test_runtime_failure_after_the_gate_still_exits_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AT-14. Mutation: classify every exception after the gate as usage."""
    monkeypatch.setattr(
        "decoy_engine.run_pipeline", mock.Mock(side_effect=RuntimeError("engine blew up"))
    )
    result = runner.invoke(app, ["run", str(_write(tmp_path, _cfg(tmp_path))), "--json"])
    assert result.exit_code == EXIT_RUNTIME
    assert "error_kind" not in _json.loads(result.stdout)
