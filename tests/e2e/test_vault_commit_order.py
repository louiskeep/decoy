"""A vault (or token map) is durable BEFORE any masked output is published.

Masked output without its vault cannot be reversed, so `decoy run --vault` publishes the vault
first and only then the outputs. The engine owns the publish (0.24.0): a private stage, fsync,
an exclusive link, a directory fsync. An existing vault is refused (exit 1), never overwritten.
A failed write exits 3, writes no output and shows no path. `decoy tokenize` commits its token
map before it writes output, for the same reason.
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
from decoy.cli.exit_codes import EXIT_RUNTIME, EXIT_USAGE
from tests.csv_sources import csv_source
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
        "sources": {"a": csv_source(src)},
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
        raise OSError(28, f"No space left on device: {CANARY}")

    monkeypatch.setattr(VaultWriter, "write", _boom)


def _fail_directory_fsync(monkeypatch: pytest.MonkeyPatch) -> None:
    real = os.fsync

    def _fsync(fd: int) -> None:
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError(5, f"Input/output error: {CANARY}")
        real(fd)

    monkeypatch.setattr(os, "fsync", _fsync)


def _assert_no_output(result, root: Path, vault: Path, text: str) -> None:
    assert not list(root.rglob("out.csv")), "masked output was published without its vault"
    assert result.exit_code == EXIT_RUNTIME, result.output
    assert " ".join(text.split()) in " ".join(result.output.split())
    assert CANARY not in result.output
    assert _leftovers(vault.parent, vault.name) == []


def test_a_failed_vault_write_publishes_no_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _pipeline(tmp_path)
    vault = tmp_path / "vault.bin"
    _fail_vault_write(monkeypatch)
    for extra in ([], ["--json"]):
        result = runner.invoke(app, ["run", str(cfg), "--vault", str(vault), *extra])
        _assert_no_output(result, tmp_path, vault, _vault_failed_text())
        assert not vault.exists()


def test_a_failed_directory_fsync_publishes_no_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The engine keeps the vault after a directory fsync failure; the CLI writes no output."""
    cfg = _pipeline(tmp_path)
    vault = tmp_path / "vault.bin"
    _fail_directory_fsync(monkeypatch)
    result = runner.invoke(app, ["run", str(cfg), "--vault", str(vault)])
    _assert_no_output(result, tmp_path, vault, "vault_commit_failed")
    assert vault.exists(), "the engine's linked vault was removed"
    assert stat.S_IMODE(vault.stat().st_mode) == 0o600
    assert "remove the vault file before rerunning" in " ".join(result.output.split())
    monkeypatch.undo()
    rerun = runner.invoke(app, ["run", str(cfg), "--vault", str(vault)])
    assert rerun.exit_code == EXIT_USAGE, rerun.output
    assert "vault_exists" in rerun.output
    assert not list(tmp_path.rglob("out.csv"))


def test_a_failed_directory_fsync_json_carries_the_remove_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _pipeline(tmp_path)
    _fail_directory_fsync(monkeypatch)
    result = runner.invoke(app, ["run", str(cfg), "--vault", str(tmp_path / "v.bin"), "--json"])
    assert result.exit_code == EXIT_RUNTIME, result.output
    assert "remove the vault file before rerunning" in " ".join(result.output.split())
    assert CANARY not in result.output


def test_an_existing_vault_is_refused_before_the_masking_step(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import decoy_engine

    vault = tmp_path / "vault.bin"
    vault.write_bytes(b"keep")
    calls: list[int] = []
    real = decoy_engine.run_pipeline

    def _spy(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    import decoy_engine.execution as engine_execution

    from decoy.cli.run import _prepare

    def _spy_other(name: str, real_fn):
        def _wrapped(*args, **kwargs):
            calls.append(name)
            return real_fn(*args, **kwargs)

        return _wrapped

    monkeypatch.setattr(decoy_engine, "run_pipeline", _spy)
    monkeypatch.setattr(
        _prepare, "acquire_relation", _spy_other("acquire_relation", _prepare.acquire_relation)
    )
    monkeypatch.setattr(
        engine_execution,
        "estimate_job_capacity",
        _spy_other("estimate_job_capacity", engine_execution.estimate_job_capacity),
    )
    root = tmp_path / "second"
    for extra in ([], ["--json"]):
        result = runner.invoke(app, ["run", str(_pipeline(root)), "--vault", str(vault), *extra])
        assert result.exit_code == EXIT_USAGE, result.output
        assert "vault_exists" in result.output
        assert not list(root.rglob("out.csv"))
    # A source that cannot be read must not win over the taken vault path.
    broken = _pipeline(tmp_path / "broken")
    (tmp_path / "broken" / "a.csv").unlink()
    result = runner.invoke(app, ["run", str(broken), "--vault", str(vault)])
    assert result.exit_code == EXIT_USAGE, result.output
    assert "vault_exists" in result.output
    assert calls == [], f"work ran before the existing vault was refused: {calls}"
    assert vault.read_bytes() == b"keep"


def test_an_existing_vault_is_refused_and_left_alone(tmp_path: Path) -> None:
    vault = tmp_path / "vault.bin"
    first = runner.invoke(app, ["run", str(_pipeline(tmp_path / "first")), "--vault", str(vault)])
    assert first.exit_code == 0, first.output
    before = vault.read_bytes()
    root = tmp_path / "second"
    for extra in ([], ["--json"]):
        result = runner.invoke(app, ["run", str(_pipeline(root)), "--vault", str(vault), *extra])
        assert result.exit_code == EXIT_USAGE, result.output
        assert "vault_exists" in result.output
        assert not list(root.rglob("out.csv")), "masked output was published without its vault"
        assert vault.read_bytes() == before, "the existing vault was replaced or removed"
        assert _leftovers(vault.parent, vault.name) == []


def test_run_writes_the_vault_durably_before_any_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The vault is published first, with owner-only mode and no stage left behind."""
    from decoy_engine.vault import VaultWriter

    from decoy.cli.run import _execute as run_execute

    events: list[str] = []
    real_outputs, real_write = run_execute._write_mask_outputs, VaultWriter.write
    vault = tmp_path / "vault.bin"

    def _outputs(*a, **k):
        events.append("outputs")
        return real_outputs(*a, **k)

    def _write(self, path):
        events.append("vault_write")
        return real_write(self, path)

    monkeypatch.setattr(run_execute, "_write_mask_outputs", _outputs)
    monkeypatch.setattr(VaultWriter, "write", _write)
    result = runner.invoke(app, ["run", str(_pipeline(tmp_path)), "--vault", str(vault)])
    assert result.exit_code == 0, result.output
    assert events[: events.index("outputs") + 1] == ["vault_write", "outputs"]
    assert vault.exists()
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


def test_a_failed_tokenize_never_deletes_a_vault_it_did_not_create(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Another run created the vault between this run's check and its open; keep it."""
    import decoy_engine

    cfg = _pipeline(tmp_path, strategy="tokenize")
    vault = tmp_path / "t.db"
    other = runner.invoke(app, ["tokenize", str(cfg), "--vault", str(vault)])
    assert other.exit_code == 0, other.output
    before = vault.read_bytes()

    def _boom(*args, **kwargs):
        raise RuntimeError(CANARY)

    monkeypatch.setattr(decoy_engine, "run_pipeline", _boom)
    real_exists = Path.exists
    stale = [True]

    def _stale_exists(self: Path) -> bool:
        # Only the first look at the vault is stale: it ran before the other run created it.
        if self.name == vault.name and stale:
            stale.pop()
            return False
        return real_exists(self)

    monkeypatch.setattr(Path, "exists", _stale_exists)
    result = runner.invoke(app, ["tokenize", str(cfg), "--vault", str(vault)])
    assert result.exit_code == EXIT_RUNTIME, result.output
    monkeypatch.undo()
    assert vault.read_bytes() == before, "a vault this run did not create was removed"


def _null_token_pipeline(root: Path) -> Path:
    """A tokenize pipeline whose column is all null, so a run commits zero mappings."""
    cfg = _pipeline(root, strategy="tokenize")
    pd.DataFrame({"email": [None, None, None]}).to_csv(root / "a.csv", index=False)
    return cfg


@pytest.mark.parametrize("nulls", [False, True], ids=["mappings", "zero-mappings"])
def test_a_creator_that_fails_keeps_the_vault_a_concurrent_run_committed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, nulls: bool
) -> None:
    """A is about to take the lock, B runs to completion, A then fails: B's vault must survive.

    The guarantee: no interleaving deletes a vault whose run committed, even one that
    committed zero mappings (an empty token_map is not proof that nobody wrote it).
    """
    import decoy_engine

    from decoy.cli import _token_vault

    cfg = (_null_token_pipeline if nulls else lambda r: _pipeline(r, strategy="tokenize"))(tmp_path)
    vault = tmp_path / "t.db"
    real_lock = _token_vault.lock_exclusive
    inner: list = []
    started: list[bool] = []
    real_run = decoy_engine.run_pipeline

    def _lock_after_b_finishes(path: Path) -> int:
        if not started:
            started.append(True)
            inner.append(runner.invoke(app, ["tokenize", str(cfg), "--vault", str(vault)]))
        return real_lock(path)

    def _fail_for_a(*args, **kwargs):
        if inner:  # A's own pipeline call, after B finished
            raise RuntimeError(CANARY)
        return real_run(*args, **kwargs)

    monkeypatch.setattr(_token_vault, "lock_exclusive", _lock_after_b_finishes)
    monkeypatch.setattr(decoy_engine, "run_pipeline", _fail_for_a)
    result = runner.invoke(app, ["tokenize", str(cfg), "--vault", str(vault)])
    assert inner and inner[0].exit_code == 0, inner[0].output
    assert result.exit_code == EXIT_RUNTIME, result.output
    assert vault.exists(), "A deleted the vault B had committed"
    with _token_vault.LocalTokenVault(vault, create=False) as kept:
        assert (kept.count() == 0) is nulls


def test_a_second_tokenize_is_refused_while_another_holds_the_vault(tmp_path: Path) -> None:
    from decoy.cli import _token_vault

    cfg = _pipeline(tmp_path, strategy="tokenize")
    vault = tmp_path / "t.db"
    with _token_vault.LocalTokenVault(vault, create=True):
        result = runner.invoke(app, ["tokenize", str(cfg), "--vault", str(vault)])
        assert result.exit_code == EXIT_USAGE, result.output
        assert "vault_busy" in result.output
        assert not list(tmp_path.rglob("out.csv"))
    assert vault.exists()


def test_a_layout_fault_and_a_taken_vault_never_reach_the_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The layout refusal is raised before DuckDB staging and the capacity preflight."""
    import decoy_engine
    import decoy_engine.execution as engine_execution

    from decoy.cli.run import _prepare

    calls: list[str] = []

    def _spy(name: str, real_fn):
        def _wrapped(*args, **kwargs):
            calls.append(name)
            return real_fn(*args, **kwargs)

        return _wrapped

    monkeypatch.setattr(_prepare, "acquire_relation", _spy("acquire", _prepare.acquire_relation))
    monkeypatch.setattr(
        engine_execution,
        "estimate_job_capacity",
        _spy("capacity", engine_execution.estimate_job_capacity),
    )
    monkeypatch.setattr(decoy_engine, "run_pipeline", _spy("pipeline", decoy_engine.run_pipeline))
    cfg = _pipeline(tmp_path)
    clash = tmp_path / "out.csv"  # the target path, so vault and target collide
    clash.write_bytes(b"taken")
    missing_db = tmp_path / "missing.duckdb"
    result = runner.invoke(
        app,
        ["run", str(cfg), "--json", "--vault", str(clash), "--duckdb-source", f"a={missing_db}"],
    )
    assert result.exit_code == EXIT_USAGE, result.output
    assert "collision" in result.output.lower() or "same" in result.output.lower(), result.output
    assert "vault_exists" not in result.output
    assert calls == [], f"work ran before the layout refusal: {calls}"
    assert clash.read_bytes() == b"taken"


def test_a_refused_second_writer_can_rerun_after_the_first_fails_and_cleans_up(
    tmp_path: Path,
) -> None:
    """A holds the lock, B is refused, A fails and removes its file, then B succeeds."""
    from decoy.cli import _token_vault

    cfg = _pipeline(tmp_path, strategy="tokenize")
    vault = tmp_path / "t.db"
    a = _token_vault.LocalTokenVault(vault, create=True)
    assert a.created is True
    refused = runner.invoke(app, ["tokenize", str(cfg), "--vault", str(vault)])
    assert refused.exit_code == EXIT_USAGE, refused.output
    assert "vault_busy" in refused.output
    a.discard_unwritten()  # A fails before any commit
    a.close()
    assert not vault.exists()
    rerun = runner.invoke(app, ["tokenize", str(cfg), "--vault", str(vault)])
    assert rerun.exit_code == 0, rerun.output
    assert vault.exists()
