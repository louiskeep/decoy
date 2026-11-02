"""One secret read per command, and the owner-only `file:` secret recipe.

The run entry and the vault writer must use one admitted provider, so the secret is read
once: a secret that changes between two reads could otherwise key the output and the vault
differently. The spy wraps the engine's registered `env` / `file` providers' `resolve`, the
one place a local secret is read.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from tests.keyed_secret import TEST_MASK_SECRET, TEST_MASK_SECRET_REF

pytest.importorskip("cryptography")

runner = CliRunner()


@pytest.fixture
def reads(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    from decoy_engine.secret_providers import default_registry

    seen: list[str] = []
    for scheme in ("env", "file"):
        provider = default_registry().get(scheme)
        real = provider.resolve

        def _counting(ref, context, _real=real, _scheme=scheme):
            seen.append(_scheme)
            return _real(ref, context)

        monkeypatch.setattr(provider, "resolve", _counting)
    return seen


def _pipeline(tmp_path: Path, ref: str, *, tables: tuple[str, ...] = ("a",), vault=True) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    sources, targets, entries = {}, {}, []
    for name in tables:
        src = tmp_path / f"{name}.csv"
        pd.DataFrame({"email": [f"u{i}@{name}.example" for i in range(12)]}).to_csv(
            src, index=False
        )
        sources[name] = {"type": "file", "format": "csv", "path": str(src)}
        targets[name] = {"type": "file", "format": "csv", "path": str(tmp_path / f"{name}.out.csv")}
        column = {"name": "email", "strategy": "hash", "namespace": "em", "vault": vault}
        entries.append({"name": name, "columns": [column]})
    cfg = {
        "version": 2,
        "global_settings": {"seed": 7, "mask_secret_ref": ref},
        "sources": sources,
        "tables": entries,
        "targets": targets,
    }
    path = tmp_path / "pipeline.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _secret_file(tmp_path: Path, mode: int) -> Path:
    path = tmp_path / "mask.key"
    path.write_text(TEST_MASK_SECRET, encoding="utf-8")
    path.chmod(mode)
    return path


@pytest.mark.parametrize("scheme", ["env", "file"])
def test_each_command_reads_the_secret_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reads: list[str], scheme: str
) -> None:
    """T-4a.3: run --vault, unmask --vault and report vault each read the secret once."""
    monkeypatch.setenv("DECOY_TEST_MASK_SECRET", TEST_MASK_SECRET)
    ref = TEST_MASK_SECRET_REF if scheme == "env" else f"file:{_secret_file(tmp_path, 0o600)}"
    cfg = _pipeline(tmp_path, ref)
    vault = tmp_path / "vault.bin"
    for argv in (
        ["run", str(cfg), "--vault", str(vault)],
        ["unmask", str(cfg), str(tmp_path / "a.out.csv"), "--vault", str(vault)],
        ["report", "vault", str(vault), "--config", str(cfg)],
    ):
        reads.clear()
        result = runner.invoke(app, argv)
        assert result.exit_code == 0, result.output
        assert reads == [scheme], (argv[0], reads)


def test_chunked_multi_table_run_reads_the_secret_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reads: list[str]
) -> None:
    """A keyed chunked run with no vault: every table gets the one admitted provider."""
    monkeypatch.setenv("DECOY_TEST_MASK_SECRET", TEST_MASK_SECRET)
    cfg = _pipeline(tmp_path, TEST_MASK_SECRET_REF, tables=("a", "b"), vault=False)
    plain = runner.invoke(app, ["run", str(cfg)])
    assert plain.exit_code == 0, plain.output
    expected = {n: (tmp_path / f"{n}.out.csv").read_bytes() for n in ("a", "b")}
    reads.clear()
    result = runner.invoke(app, ["run", str(cfg), "--chunked", "--chunk-size", "5"])
    assert result.exit_code == 0, result.output
    assert reads == ["env"]
    assert {n: (tmp_path / f"{n}.out.csv").read_bytes() for n in ("a", "b")} == expected


def test_owner_only_file_secret_works(tmp_path: Path) -> None:
    """T-4a.5 (0600 half): the documented recipe, an owner-only file, is accepted."""
    key = _secret_file(tmp_path, 0o600)
    assert os.stat(key).st_mode & 0o077 == 0
    cfg = _pipeline(tmp_path, f"file:{key}")
    result = runner.invoke(app, ["run", str(cfg), "--vault", str(tmp_path / "v.bin")])
    assert result.exit_code == 0, result.output


@pytest.mark.parametrize("case", ["chunk_incompatible", "missing_source", "cloud_target"])
def test_usage_and_source_refusals_come_before_the_secret_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reads: list[str], case: str
) -> None:
    """The up-front admission must not reorder refusals the engine used to raise first."""
    monkeypatch.setenv("DECOY_TEST_MASK_SECRET", TEST_MASK_SECRET)
    cfg_path = _pipeline(tmp_path, TEST_MASK_SECRET_REF, vault=False)
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    argv = ["run", str(cfg_path)]
    if case == "chunk_incompatible":
        cfg["tables"][0]["columns"].append({"name": "email2", "strategy": "shuffle"})
        argv.append("--chunked")
    elif case == "missing_source":
        cfg["sources"]["a"]["path"] = str(tmp_path / "absent.csv")
    else:
        cfg["targets"]["a"] = {"type": "gcs", "format": "csv", "bucket": "b", "object": "a.csv"}
    cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    result = runner.invoke(app, argv)
    expected = {
        "chunk_incompatible": "value-keyed",
        "missing_source": "absent.csv",
        "cloud_target": "cannot run through",
    }[case]
    assert expected in " ".join(result.output.split()), result.output
    assert reads == [], (case, result.output)
