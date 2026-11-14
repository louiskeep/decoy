"""AT-11 (P9): `unmask` and `detokenize` of a run's fixed-width target, and their default names.

A file in `out/<name>/<run-id>/` is the declared target, so it is read in the declared format
by run path and through `current`; a copy at the old YAML-folder place still is. The default
output sits beside the input with the `current` link resolved first. `side_file_default` is the
one table of those names.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_OK, EXIT_USAGE
from decoy.cli.io import _layout
from tests.e2e.cli_fmt.test_target_format_dispatch import _target, _target_layout
from tests.e2e.cli_fmt.test_target_format_readers import (
    _EMAILS,
    _VAULT_EMAILS,
    _fw_layout,
    _token_width,
    _vault_config,
)
from tests.e2e.test_tokenize_cli import _TOKENIZE_COLS
from tests.e2e.test_tokenize_cli import _pipeline as _tokenize_pipeline

pytestmark = pytest.mark.usefixtures("mask_secret")
needs_vault = pytest.mark.skipif(
    importlib.util.find_spec("cryptography") is None, reason="the vault needs cryptography"
)
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="current is a symlink on POSIX")
runner = CliRunner()


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "pipelines" / "orders").mkdir(parents=True)
    (root / "decoy.yaml").write_text("kind: decoy-project/v1\n", encoding="utf-8")
    return root


def _run_dir(root: Path) -> Path:
    (run,) = [p for p in (root / "out" / "orders").iterdir() if p.is_dir() and p.name[0].isdigit()]
    return run


def _invoke(root: Path, monkeypatch: pytest.MonkeyPatch, *args: str) -> Any:
    monkeypatch.chdir(root)
    return runner.invoke(app, list(args))


def _mask_run(root: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, pd.DataFrame]:
    """A fixed-width masked run of `orders` with a hash vault column; returns run, vault, frame."""
    d = root / "pipelines" / "orders"
    probe = root.parent / "probe"
    probe.mkdir()
    _vault_config(probe, _target("csv", probe / "m.csv"))
    vault = root / "vault.bin"
    assert (
        runner.invoke(
            app, ["run", str(probe / "pipeline.yaml"), "--vault", str(root / "probe.vault")]
        ).exit_code
        == EXIT_OK
    )
    layout = _target_layout(pd.read_csv(probe / "m.csv", dtype=str))
    layout = {"columns": [{**c, "type": "str"} for c in layout["columns"]]}
    _vault_config(d, {"format": "fixed_width", "path": "masked.txt", "layout": layout})
    result = _invoke(root, monkeypatch, "run", "orders", "--vault", str(vault))
    assert result.exit_code == EXIT_OK, result.output
    run = _run_dir(root)
    from decoy_engine import read_fixed_width

    return run, vault, read_fixed_width(run / "masked.txt", layout)


def _assert_recovered(out: Path, masked: pd.DataFrame) -> None:
    got = pd.read_csv(out, dtype=str)
    assert got["email"].tolist() == _VAULT_EMAILS
    assert got["id"].tolist() == masked["id"].tolist()


@needs_vault
def test_unmask_reads_a_run_target_by_run_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path)
    run, vault, masked = _mask_run(root, monkeypatch)
    result = _invoke(
        root, monkeypatch, "unmask", "orders", str(run / "masked.txt"), "--vault", str(vault)
    )
    assert result.exit_code == EXIT_OK, result.output
    _assert_recovered(run / "masked.unmasked.csv", masked)


@needs_vault
@posix_only
def test_unmask_through_current_writes_into_the_run_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path)
    run, vault, masked = _mask_run(root, monkeypatch)
    through = root / "out" / "orders" / "current" / "masked.txt"
    result = _invoke(root, monkeypatch, "unmask", "orders", str(through), "--vault", str(vault))
    assert result.exit_code == EXIT_OK, result.output
    _assert_recovered(run / "masked.unmasked.csv", masked)
    assert not any(p.name.endswith(".unmasked.csv") for p in (root / "out" / "orders").glob("*"))


@needs_vault
def test_unmask_still_reads_the_old_yaml_folder_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path)
    run, vault, masked = _mask_run(root, monkeypatch)
    old = root / "pipelines" / "orders" / "masked.txt"
    shutil.copy(run / "masked.txt", old)
    result = _invoke(root, monkeypatch, "unmask", "orders", str(old), "--vault", str(vault))
    assert result.exit_code == EXIT_OK, result.output
    _assert_recovered(old.with_name("masked.unmasked.csv"), masked)


def _tokenized_run(root: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    d = root / "pipelines" / "orders"
    cfg = _tokenize_pipeline(
        d, _TOKENIZE_COLS, out_name="tok.txt", out_format="fixed_width", emails=_EMAILS
    )
    raw = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    raw["targets"]["people"]["path"] = "tok.txt"
    raw["targets"]["people"]["layout"] = _fw_layout(_token_width(root.parent))
    cfg.write_text(yaml.safe_dump(raw), encoding="utf-8")
    vault = root / "tokens.db"
    result = _invoke(root, monkeypatch, "tokenize", "orders", "--vault", str(vault))
    assert result.exit_code == EXIT_OK, result.output
    return _run_dir(root), vault


@needs_vault
def test_detokenize_reads_a_run_target_by_run_path_and_current(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path)
    run, vault = _tokenized_run(root, monkeypatch)
    result = _invoke(
        root, monkeypatch, "detokenize", "orders", str(run / "tok.txt"), "--vault", str(vault)
    )
    assert result.exit_code == EXIT_OK, result.output
    got = pd.read_csv(run / "tok.detokenized.csv", dtype=str)
    assert got["email"].tolist() == _EMAILS
    (run / "tok.detokenized.csv").unlink()
    if sys.platform != "win32":
        through = root / "out" / "orders" / "current" / "tok.txt"
        result = _invoke(
            root, monkeypatch, "detokenize", "orders", str(through), "--vault", str(vault)
        )
        assert result.exit_code == EXIT_OK, result.output
        assert pd.read_csv(run / "tok.detokenized.csv", dtype=str)["email"].tolist() == _EMAILS


@needs_vault
def test_detokenize_refuses_to_overwrite_its_default_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path)
    run, vault = _tokenized_run(root, monkeypatch)
    args = ["detokenize", "orders", str(run / "tok.txt"), "--vault", str(vault)]
    assert _invoke(root, monkeypatch, *args).exit_code == EXIT_OK
    again = _invoke(root, monkeypatch, *args)
    assert again.exit_code == EXIT_USAGE
    assert "detokenize_output_exists" in again.output
    assert "a@x.com" not in again.output


@pytest.mark.parametrize(
    ("kind", "name", "expected"),
    [
        ("unmasked", "m.csv", "m.unmasked.csv"),
        ("unmasked", "m.masked.csv", "m.masked.unmasked.csv"),
        ("snapshot", "customers.csv", "customers.snapshot.json"),
        ("detokenized", "t.csv", "t.detokenized.csv"),
        ("detokenized", "t.txt", "t.detokenized.csv"),
    ],
)
def test_side_file_default_names_beside_the_input(
    tmp_path: Path, kind: str, name: str, expected: str
) -> None:
    assert _layout.side_file_default(kind, tmp_path / name) == tmp_path / expected


def test_side_file_default_parquet_form_for_detokenized(tmp_path: Path) -> None:
    got = _layout.side_file_default("detokenized", tmp_path / "t.pq", parquet=True)
    assert got == tmp_path / "t.detokenized.parquet"


@posix_only
def test_side_file_default_resolves_a_linked_folder_first(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    os.symlink(real, tmp_path / "current")
    assert _layout.side_file_default("unmasked", tmp_path / "current" / "m.csv") == (
        real.resolve() / "m.unmasked.csv"
    )
