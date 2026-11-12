"""`decoy run --json` carries the engine's reason for an engine-raised failure, and none for a
refusal the CLI itself owns. The reason is computed from the exception as raised."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy import _resources
from decoy.__main__ import app
from decoy.cli.extras import MissingExtraError
from decoy.cli.run import _errors
from tests.csv_sources import csv_source

runner = CliRunner()
MARKER = "zz_marker_exc"


def _config(tmp_path: Path) -> Path:
    src = tmp_path / "in.csv"
    pd.DataFrame({"code": ["AAAAA", "BBBBB"]}).to_csv(src, index=False)
    cfg = {
        "version": 2,
        "global_settings": {"seed": 7},
        "sources": {"t": csv_source(src)},
        "tables": [{"name": "t", "columns": [{"name": "code", "strategy": "redact"}]}],
        "targets": {"t": {"type": "file", "format": "csv", "path": str(tmp_path / "out.csv")}},
    }
    p = tmp_path / "pipeline.yaml"
    p.write_text(yaml.dump(cfg), encoding="utf-8")
    return p


def _run_failing(tmp_path: Path, exc: BaseException) -> tuple[int, dict, str]:
    cfg = _config(tmp_path)
    with mock.patch("decoy_engine.run_pipeline", side_effect=exc):
        result = runner.invoke(app, ["run", str(cfg), "--json"])
    return result.exit_code, json.loads(result.output), result.output


def _gate_refusal(exit_code: int, kind: str):
    from decoy.cli.gate import PreRunCheckError

    return PreRunCheckError(
        "refused", exit_code=exit_code, error_kind=kind, code=None, extra=None, messages=[]
    )


def test_capacity_failure_carries_reason(tmp_path: Path) -> None:
    from decoy_engine.execution import ExecutionError

    code, payload, _ = _run_failing(
        tmp_path, ExecutionError(code="out_of_core_insufficient_memory", message=MARKER)
    )
    assert code == 5
    assert payload["error_kind"] == "capacity"
    assert payload["code"] == "out_of_core_insufficient_memory"
    assert payload["reason"]["namespace"] == "runtime"
    assert payload["reason"]["code"] == "out_of_core_insufficient_memory"
    assert MARKER not in json.dumps(payload["reason"])


def test_publication_failure(tmp_path: Path) -> None:
    from decoy_engine.execution._isolated_commit import CommitError

    code, payload, _ = _run_failing(tmp_path, CommitError(MARKER))
    assert code == 3
    assert (payload["reason"]["namespace"], payload["reason"]["code"]) == (
        "decoy",
        "publication_failed",
    )


def test_config_failure(tmp_path: Path) -> None:
    from decoy_engine import ConfigError

    code, payload, _ = _run_failing(tmp_path, ConfigError(MARKER))
    assert code == 1
    assert payload["reason"]["retry_class"] == "configuration_repair"


def test_unknown_exception(tmp_path: Path) -> None:
    class Unregistered(ValueError):
        code = MARKER

    code, payload, _ = _run_failing(tmp_path, Unregistered("boom"))
    assert code == 3
    assert (payload["reason"]["namespace"], payload["reason"]["code"]) == (
        "decoy",
        "unexpected_error",
    )
    assert MARKER not in json.dumps(payload["reason"])


def test_rewrites_keep_the_original_reason(tmp_path: Path) -> None:
    from decoy_engine.detection.ner import NerUnavailableError
    from decoy_engine.reason_adapter import reason_from_exception

    code, payload, _ = _run_failing(tmp_path, ModuleNotFoundError("no boto3", name="boto3"))
    assert (code, payload["error_kind"]) == (1, "missing_extra")
    assert "reason" not in payload

    def ner() -> NerUnavailableError:
        return NerUnavailableError(code="ner_spacy_not_installed", message=MARKER)

    code, payload, _ = _run_failing(tmp_path, ner())
    assert (code, payload["error_kind"]) == (1, "missing_extra")
    assert payload["reason"] == reason_from_exception(ner()).to_payload()
    assert payload["reason"]["code"] != "unexpected_error"


def _make(cls: type) -> BaseException:
    special = {
        _resources.ResourceError: lambda: _resources.ResourceError("zz", "size"),
        MissingExtraError: lambda: MissingExtraError(MARKER, extra="cloud"),
    }
    if cls in special:
        return special[cls]()
    for args in ((MARKER,), (MARKER, MARKER)):
        try:
            return cls(*args)
        except TypeError:
            continue
    return cls(MARKER, code=MARKER)


def _refusal_ids() -> list[str]:
    return [t.__name__ for t in _errors._cli_refusal_types()]


@pytest.mark.parametrize("index", range(len(_errors._cli_refusal_types()) or 1), ids=_refusal_ids())
def test_cli_owned_refusals_have_no_reason(tmp_path: Path, index: int) -> None:
    types = _errors._cli_refusal_types()
    assert types, "the CLI-owned refusal set is empty"
    if types[index] is _errors.PreRunCheckError:
        exc = _gate_refusal(1, "validation")
    else:
        exc = _make(types[index])
    code, payload, _ = _run_failing(tmp_path, exc)
    assert "reason" not in payload
    assert code in {1, 3}


@pytest.mark.parametrize(("exit_code", "kind"), [(1, "validation"), (5, "capacity")])
def test_gate_refusals_have_no_reason(tmp_path: Path, exit_code: int, kind: str) -> None:
    code, payload, _ = _run_failing(tmp_path, _gate_refusal(exit_code, kind))
    assert code == exit_code
    assert "reason" not in payload


def test_required_refusals_are_cli_owned() -> None:
    names = {t.__name__ for t in _errors._cli_refusal_types()}
    assert {
        "_VaultUsageError",
        "_ChunkedVaultError",
        "_VaultWriteError",
        "OutDirUsageError",
        "PreRunCheckError",
        "_OtelSettingsUsageError",
    } <= names


def test_usage_types_single_source(tmp_path: Path) -> None:
    from decoy_engine import ConfigError, PipelineValidationError
    from decoy_engine.detection.ner import NerUnavailableError
    from decoy_engine.keyprovider import MaskSecretError
    from decoy_engine.plan import PlanCompileError

    from decoy import _native_gate
    from decoy.cli.extras import UnsupportedCloudEndpointError
    from decoy.cli.io import DuckDBSourceError, LayoutError, TargetFormatError
    from decoy.cli.run import _execute, _notify, _prepare, _vault

    base = (
        PlanCompileError,
        PipelineValidationError,
        ConfigError,
        _execute._ChunkedGenerateError,
        _execute._ChunkedFixedWidthError,
        _execute._ChunkedIntegrityError,
        _execute._ChunkedQuarantineError,
        TargetFormatError,
        LayoutError,
        _execute._ChunkedReportFlagError,
        _vault._ChunkedVaultError,
        _vault._VaultUsageError,
        _prepare._MaskSecretUsageError,
        _notify._OtelSettingsUsageError,
        _resources.ResourceError,
        DuckDBSourceError,
        _errors.OutDirUsageError,
        MissingExtraError,
        UnsupportedCloudEndpointError,
        NerUnavailableError,
        _native_gate.NativeGateError,
        MaskSecretError,
    )
    assert _errors._usage_types() == base

    # One source: a type added to `_usage_types()` alone is exit 1 and carries no reason.
    class Sentinel(Exception):
        pass

    with mock.patch.object(_errors, "_usage_types", lambda: (*base, Sentinel)):
        code, payload, _ = _run_failing(tmp_path, Sentinel(MARKER))
    assert code == 1
    assert "reason" not in payload


def _usage() -> BaseException:
    from decoy_engine import ConfigError

    return ConfigError("bad")


def _capacity() -> BaseException:
    from decoy_engine.execution import ExecutionError

    return ExecutionError(code="out_of_core_insufficient_memory", message="m")


@pytest.mark.parametrize(
    ("make", "expected"),
    [(_usage, 1), (lambda: RuntimeError("boom"), 3), (_capacity, 5)],
    ids=["usage", "runtime", "capacity"],
)
def test_classifier_failure_keeps_exit(tmp_path: Path, make, expected: int) -> None:
    broken = mock.patch(
        "decoy_engine.reason_adapter.registered_families", side_effect=RuntimeError(MARKER)
    )
    with broken:
        code, payload, out = _run_failing(tmp_path, make())
    assert code == expected
    assert "reason" not in payload
    assert MARKER not in out
