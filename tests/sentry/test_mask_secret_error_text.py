"""Secret refusals and `decoy unmask` failures print constant, value-free text.

Every CLI surface that admits the mask secret maps a `MaskSecretError` by its registered code to
fixed text from `decoy._mask_secret_guidance`, exit 1. Nothing from the exception's message,
the ref, a path or a cell can ride along, because the printed text is a constant. The doubles
below put a canary in the engine message to prove the CLI never prints it. `decoy unmask`
dispatches on the secret code BEFORE its class branches, so a class that is also an
`ExecutionError`, `ConfigError` or `VaultError` still gets the secret remedy.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml
from tests.keyed_secret import TEST_MASK_SECRET, TEST_MASK_SECRET_REF
from typer.testing import CliRunner

from decoy import _mask_secret_guidance as guidance
from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_RUNTIME, EXIT_USAGE

pytest.importorskip("cryptography")

runner = CliRunner()

CANARY = "canary-7f3e9a1c-cell-value"
_CODES = (
    "keyed_strategy_requires_secret",
    "weak_mask_secret",
    "missing_mask_secret",
    "secret_file_permissions_unsafe",
)


def _pipeline(tmp_path: Path, ref: str, *, tokenize: bool = False) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    src = tmp_path / "a.csv"
    pd.DataFrame({"email": [CANARY, "b@example.com", "c@example.com"]}).to_csv(src, index=False)
    column = (
        {"name": "email", "strategy": "tokenize", "namespace": "em"}
        if tokenize
        else {"name": "email", "strategy": "hash", "namespace": "em", "vault": True}
    )
    cfg = {
        "version": 2,
        "global_settings": {"seed": 3, "mask_secret_ref": ref},
        "sources": {"a": {"type": "file", "format": "csv", "path": str(src)}},
        "tables": [{"name": "a", "columns": [column]}],
        "targets": {"a": {"type": "file", "format": "csv", "path": str(tmp_path / "out.csv")}},
    }
    path = tmp_path / "pipeline.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


@pytest.fixture
def written(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """A real masked file and vault, written under the test secret."""
    monkeypatch.setenv("DECOY_TEST_MASK_SECRET", TEST_MASK_SECRET)
    cfg = _pipeline(tmp_path / "ok", TEST_MASK_SECRET_REF)
    vault = tmp_path / "ok" / "vault.bin"
    assert runner.invoke(app, ["run", str(cfg), "--vault", str(vault)]).exit_code == 0
    return tmp_path / "ok" / "out.csv", vault


def _unsafe_ref(tmp_path: Path) -> str:
    key = tmp_path / f"{CANARY}.key"
    key.write_text(TEST_MASK_SECRET, encoding="utf-8")
    key.chmod(0o644)
    return f"file:{key}"


def _double(base: type[Exception] | None, code: str):
    from decoy_engine.keyprovider import MaskSecretError

    def _init(self, *, code: str, message: str) -> None:
        Exception.__init__(self, message)
        self.code, self.message = code, message

    bases = (MaskSecretError,) if base is None else (MaskSecretError, base)
    cls = type("_Double", bases, {"__init__": _init, "__str__": lambda self: self.message})

    def _raise(*_a, **_k):
        raise cls(code=code, message=f"{CANARY} {TEST_MASK_SECRET_REF}")

    return _raise


def _argv(surface: str, tmp_path: Path, written: tuple[Path, Path]) -> list[str]:
    masked, vault = written
    ref = _unsafe_ref(tmp_path)
    cfg = _pipeline(tmp_path / "bad", ref, tokenize=surface == "tokenize")
    return {
        "run": ["run", str(cfg), "--vault", str(tmp_path / "fresh.bin")],
        "tokenize": ["tokenize", str(cfg), "--vault", str(tmp_path / "tokens.db")],
        "unmask": ["unmask", str(cfg), str(masked), "--vault", str(vault)],
        "report_vault": ["report", "vault", str(vault), "--config", str(cfg)],
    }[surface]


_PATCH = {
    "run": "decoy_engine.secret_providers.admit_mask_key",
    "tokenize": "decoy_engine.run_pipeline",
    "unmask": "decoy_engine.unmask_pipeline",
    "report_vault": "decoy_engine.secret_providers.admit_mask_key",
}
_KEYED = {
    "run": "RUN",
    "tokenize": "TOKENIZE",
    "unmask": "UNMASK",
    "report_vault": "REPORT_VAULT",
}


def _expected(surface: str, code: str) -> str:
    # Looked up at run time so the red run names the missing text, not a collection error.
    if code == guidance.CODE:
        return getattr(guidance, _KEYED[surface], f"<no {_KEYED[surface]}>")
    return getattr(guidance, "SECRET_REMEDIES", {}).get(code, f"<no remedy for {code}>")


def _assert_value_free(result, tmp_path: Path) -> None:
    for needle in (CANARY, TEST_MASK_SECRET, TEST_MASK_SECRET_REF, "0644", "Traceback"):
        assert needle not in result.output, (needle, result.output)
    assert not (tmp_path / "fresh.bin").exists() and not (tmp_path / "bad" / "out.csv").exists()


@pytest.mark.parametrize("code", _CODES)
@pytest.mark.parametrize("surface", ["run", "tokenize", "unmask", "report_vault"])
def test_secret_refusal_prints_a_constant_remedy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, written, surface: str, code: str
) -> None:
    """T-4b.1 / T-4a.5: constant text per code, exit 1, no canary in text or JSON."""
    argv = _argv(surface, tmp_path, written)
    monkeypatch.setattr(_PATCH[surface], _double(None, code))
    expected = _expected(surface, code)
    for extra in ([], ["--json"], ["--quiet"]):
        result = runner.invoke(app, [*argv, *extra])
        assert result.exit_code == EXIT_USAGE, result.output
        _assert_value_free(result, tmp_path)
        if extra == ["--json"]:
            assert json.loads(result.stdout)["error"] == expected
        elif not extra:
            assert " ".join(expected.split()) in " ".join(result.output.split())
    if code == "secret_file_permissions_unsafe":
        assert "owner-only" in expected and expected.startswith(f"{code}: ")


@pytest.mark.parametrize("base", ["ExecutionError", "ConfigError", "VaultError"])
def test_unmask_dispatches_on_the_secret_code_before_the_class(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, written, base: str
) -> None:
    import decoy_engine
    from decoy_engine.errors import ConfigError
    from decoy_engine.execution import ExecutionError

    cls = {"ExecutionError": ExecutionError, "ConfigError": ConfigError}.get(
        base, decoy_engine.VaultError
    )
    monkeypatch.setattr(_PATCH["unmask"], _double(cls, guidance.CODE))
    result = runner.invoke(app, [*_argv("unmask", tmp_path, written), "--json"])
    assert result.exit_code == EXIT_USAGE, result.output
    assert json.loads(result.stdout)["error"] == guidance.UNMASK
    _assert_value_free(result, tmp_path)


def test_unmask_runtime_failure_prints_the_type_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, written
) -> None:
    def _boom(*_a, **_k):
        raise RuntimeError(f"bad row {CANARY}")

    monkeypatch.setattr("decoy_engine.unmask_pipeline", _boom)
    masked, _ = written
    cfg = _pipeline(tmp_path / "ok", TEST_MASK_SECRET_REF)
    for extra in ([], ["--json"]):
        result = runner.invoke(app, ["unmask", str(cfg), str(masked), *extra])
        assert result.exit_code == EXIT_RUNTIME, result.output
        assert "unmask failed: RuntimeError" in result.output
        assert CANARY not in result.output


def test_unreadable_masked_csv_prints_the_path_and_type_not_the_cell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, written
) -> None:
    """T-4b.3 (F-5): a parse error can quote a cell; only the given path and the type print."""
    import pandas

    def _parse_error(*_a, **_k):
        raise pandas.errors.ParserError(f"unexpected field near {CANARY!r}")

    masked, _ = written
    cfg = _pipeline(tmp_path / "ok", TEST_MASK_SECRET_REF)
    monkeypatch.setattr(pandas, "read_csv", _parse_error)
    for extra in ([], ["--json"]):
        result = runner.invoke(app, ["unmask", str(cfg), str(masked), *extra])
        assert result.exit_code == EXIT_USAGE, result.output
        flat = "".join(result.output.split())
        assert "".join(str(masked).split()) in flat and "ParserError" in flat
        assert CANARY not in result.output
