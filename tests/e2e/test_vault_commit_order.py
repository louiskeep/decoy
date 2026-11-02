"""A vault (or token map) is durable BEFORE any masked output is published.

Masked output without its vault cannot be reversed, so `decoy run --vault` writes the vault
first: a 0600 temp file in the vault's directory, fsync, rename, fsync the directory, and only
then the outputs. Any failure on that path exits 3 with the constant `vault_write_failed` text,
writes no output and leaves no vault or temp file; a vault renamed in before a failed directory
fsync is removed, and a pre-existing vault survives a failed rewrite. `decoy tokenize` commits
its token map before it writes output, for the same reason.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_RUNTIME
from tests.keyed_secret import TEST_MASK_SECRET_REF

pytest.importorskip("cryptography")
pytestmark = pytest.mark.usefixtures("mask_secret")

runner = CliRunner()
SOURCE = ["alice@example.com", "bob@example.com", "carol@example.com"]
CANARY = "canary-vault-9b2d"


@pytest.fixture
def mask_secret(monkeypatch: pytest.MonkeyPatch) -> str:
    from tests.keyed_secret import TEST_MASK_SECRET, TEST_MASK_SECRET_ENV

    monkeypatch.setenv(TEST_MASK_SECRET_ENV, TEST_MASK_SECRET)
    return TEST_MASK_SECRET_REF


def _pipeline(root: Path, *, strategy: str = "hash") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    src = root / "a.csv"
    pd.DataFrame({"email": SOURCE}).to_csv(src, index=False)
    column: dict = {"name": "email", "strategy": strategy, "namespace": "em"}
    if strategy == "hash":
        column["vault"] = True
    cfg = {
        "version": 2,
        "global_settings": {"seed": 3, "mask_secret_ref": TEST_MASK_SECRET_REF},
        "sources": {"a": {"type": "file", "format": "csv", "path": str(src)}},
        "tables": [{"name": "a", "columns": [column]}],
        "targets": {"a": {"type": "file", "format": "csv", "path": str(root / "out.csv")}},
    }
    path = root / "pipeline.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _vault_failed_text() -> str:
    from decoy.cli import run as run_mod

    return getattr(run_mod, "VAULT_WRITE_FAILED", "<no VAULT_WRITE_FAILED constant>")


def _leftovers(directory: Path, vault_name: str) -> list[str]:
    return sorted(p.name for p in directory.iterdir() if p.name.startswith(f".{vault_name}"))


def _fail_vault_write(monkeypatch: pytest.MonkeyPatch) -> None:
    from decoy_engine.vault import VaultWriter

    def _boom(self, path):
        Path(path).write_bytes(b"partial")
        raise OSError(28, f"No space left on device: {CANARY}")

    monkeypatch.setattr(VaultWriter, "write", _boom)


def _fail_directory_fsync(monkeypatch: pytest.MonkeyPatch) -> None:
    real = os.fsync

    def _fsync(fd: int) -> None:
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError(5, f"Input/output error: {CANARY}")
        real(fd)

    monkeypatch.setattr(os, "fsync", _fsync)


def _assert_failed_clean(result, root: Path, vault: Path) -> None:
    assert not (root / "out.csv").exists(), "masked output was published without its vault"
    assert result.exit_code == EXIT_RUNTIME, result.output
    flat = " ".join(result.output.split())
    assert " ".join(_vault_failed_text().split()) in flat
    assert CANARY not in result.output
    assert _leftovers(vault.parent, vault.name) == []


@pytest.mark.parametrize("fault", ["vault_write", "directory_fsync"])
def test_failed_vault_write_publishes_no_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    cfg = _pipeline(tmp_path)
    vault = tmp_path / "vault.bin"
    (_fail_vault_write if fault == "vault_write" else _fail_directory_fsync)(monkeypatch)
    for extra in ([], ["--json"]):
        result = runner.invoke(app, ["run", str(cfg), "--vault", str(vault), *extra])
        _assert_failed_clean(result, tmp_path, vault)
        assert not vault.exists(), "a vault renamed in before a failed fsync must be removed"


@pytest.mark.parametrize("fault", ["vault_write", "directory_fsync"])
def test_a_pre_existing_vault_survives_a_failed_rewrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    vault = tmp_path / "vault.bin"
    first = runner.invoke(app, ["run", str(_pipeline(tmp_path / "first")), "--vault", str(vault)])
    assert first.exit_code == 0, first.output
    before = vault.read_bytes()
    (_fail_vault_write if fault == "vault_write" else _fail_directory_fsync)(monkeypatch)
    root = tmp_path / "second"
    result = runner.invoke(app, ["run", str(_pipeline(root)), "--vault", str(vault)])
    _assert_failed_clean(result, root, vault)
    assert vault.read_bytes() == before


def test_run_writes_the_vault_durably_before_any_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Temp write, data fsync, rename, directory fsync, and only then the outputs."""
    from decoy_engine.vault import VaultWriter

    from decoy.cli import run as run_mod

    events: list[str] = []
    real_outputs, real_write = run_mod._write_mask_outputs, VaultWriter.write
    real_replace, real_fsync = os.replace, os.fsync
    vault = tmp_path / "vault.bin"

    def _outputs(*a, **k):
        events.append("outputs")
        return real_outputs(*a, **k)

    def _write(self, path):
        events.append("vault_write")
        return real_write(self, path)

    def _replace(src, dst, *a, **k):
        if Path(dst) == vault:
            events.append("vault_rename")
        return real_replace(src, dst, *a, **k)

    def _fsync(fd: int) -> None:
        events.append("fsync_dir" if stat.S_ISDIR(os.fstat(fd).st_mode) else "fsync_file")
        real_fsync(fd)

    monkeypatch.setattr(run_mod, "_write_mask_outputs", _outputs)
    monkeypatch.setattr(VaultWriter, "write", _write)
    monkeypatch.setattr(os, "replace", _replace)
    monkeypatch.setattr(os, "fsync", _fsync)
    result = runner.invoke(app, ["run", str(_pipeline(tmp_path)), "--vault", str(vault)])
    assert result.exit_code == 0, result.output
    assert events[: events.index("outputs") + 1] == [
        "vault_write",
        "fsync_file",
        "vault_rename",
        "fsync_dir",
        "outputs",
    ]
    assert stat.S_IMODE(vault.stat().st_mode) == 0o600
    assert _leftovers(tmp_path, vault.name) == []


def test_tokenize_commits_the_token_map_before_any_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from decoy.cli import _token_vault
    from decoy.cli import run as run_mod

    events: list[str] = []
    real_outputs, real_commit = run_mod._write_mask_outputs, _token_vault.LocalTokenVault.commit

    def _outputs(*a, **k):
        events.append("outputs")
        return real_outputs(*a, **k)

    def _commit(self):
        events.append("commit")
        return real_commit(self)

    monkeypatch.setattr(run_mod, "_write_mask_outputs", _outputs)
    monkeypatch.setattr(_token_vault.LocalTokenVault, "commit", _commit)
    cfg = _pipeline(tmp_path, strategy="tokenize")
    result = runner.invoke(app, ["tokenize", str(cfg), "--vault", str(tmp_path / "tokens.db")])
    assert result.exit_code == 0, result.output
    assert events == ["commit", "outputs"]


def test_tokenize_failed_commit_publishes_no_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from decoy.cli import _token_vault

    def _boom(self):
        raise OSError(28, f"No space left on device: {CANARY}")

    monkeypatch.setattr(_token_vault.LocalTokenVault, "commit", _boom)
    cfg = _pipeline(tmp_path, strategy="tokenize")
    vault = tmp_path / "tokens.db"
    result = runner.invoke(app, ["tokenize", str(cfg), "--vault", str(vault)])
    assert result.exit_code == EXIT_RUNTIME, result.output
    assert CANARY not in result.output
    assert not (tmp_path / "out.csv").exists(), "tokenized output was published uncommitted"
    assert not vault.exists()


@pytest.mark.parametrize("also_fail_directory_fsync", [False, True])
def test_preexisting_vault_survives_backup_link_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, also_fail_directory_fsync: bool
) -> None:
    """An existing vault that cannot be backed up is never overwritten: abort before the rename."""
    import errno

    vault = tmp_path / "vault.bin"
    first = runner.invoke(app, ["run", str(_pipeline(tmp_path / "first")), "--vault", str(vault)])
    assert first.exit_code == 0, first.output
    before = vault.read_bytes()
    attempts: list[tuple[str, str]] = []
    real_link = os.link

    def _link(src, dst, *a, **k):
        if Path(src) == vault:
            attempts.append((str(src), str(dst)))
            raise OSError(errno.EPERM, f"Operation not permitted: {CANARY}")
        return real_link(src, dst, *a, **k)

    monkeypatch.setattr(os, "link", _link)
    if also_fail_directory_fsync:
        _fail_directory_fsync(monkeypatch)
    root = tmp_path / "second"
    for extra in ([], ["--json"]):
        result = runner.invoke(app, ["run", str(_pipeline(root)), "--vault", str(vault), *extra])
        _assert_failed_clean(result, root, vault)
        assert vault.read_bytes() == before, "the pre-existing vault was replaced or removed"
    assert len(attempts) == 2, "the backup link was never attempted; the test is vacuous"
