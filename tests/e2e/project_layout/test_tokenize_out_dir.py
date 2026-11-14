"""P9: `decoy tokenize --out-dir DIR` places its targets like `decoy run --out-dir DIR`.

DIR stands in for the run folder: relative to the current folder, made owner-only after the gate,
no claim, run id or `current` link, files overwritten. `--vault` stays a path typed relative to the
current folder. Every refusal exits 1 before a source is read or a folder is made.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_OK, EXIT_USAGE
from tests.e2e.test_tokenize_cli import _TOKENIZE_COLS
from tests.e2e.test_tokenize_cli import _pipeline as _tokenize_pipeline

pytestmark = pytest.mark.usefixtures("mask_secret")
runner = CliRunner()
EMAILS = ["a@x.com", "b@y.com", "a@x.com"]


def _project(tmp_path: Path, target: str = "tok.csv") -> Path:
    root = tmp_path / "proj"
    d = root / "pipelines" / "orders"
    d.mkdir(parents=True)
    (root / "decoy.yaml").write_text("kind: decoy-project/v1\n", encoding="utf-8")
    cfg = _tokenize_pipeline(d, _TOKENIZE_COLS, out_name="tok.csv", emails=EMAILS)
    raw = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    raw["targets"]["people"]["path"] = target
    cfg.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return root


def _tokenize(root: Path, monkeypatch: pytest.MonkeyPatch, *args: str) -> Any:
    monkeypatch.chdir(root)
    return runner.invoke(app, ["tokenize", "orders", *args], catch_exceptions=False)


def _files(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*")}


def _no_source_read(monkeypatch: pytest.MonkeyPatch) -> None:
    import decoy.cli.run as run_module

    def boom(*_a: object, **_k: object) -> None:
        raise AssertionError("a source was read before the refusal")

    monkeypatch.setattr(run_module, "_load_sources_from_config", boom)


def test_targets_land_in_dir_and_no_run_folder_is_made(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path)
    result = _tokenize(root, monkeypatch, "--out-dir", "build", "--vault", "v.db")
    assert result.exit_code == EXIT_OK, result.output
    assert (root / "build" / "tok.csv").is_file()
    assert (root / "v.db").is_file()
    assert not (root / "out").exists()
    assert "a@x.com" not in (root / "build" / "tok.csv").read_text(encoding="utf-8")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX modes")
def test_dir_is_relative_to_the_current_folder_and_owner_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path)
    assert _tokenize(root, monkeypatch, "--out-dir", "a/b", "--vault", "v.db").exit_code == 1
    assert not (root / "a").exists()
    assert _tokenize(root, monkeypatch, "--out-dir", "b", "--vault", "v.db").exit_code == EXIT_OK
    assert ((root / "b").stat().st_mode & 0o077) == 0
    assert not (root / "pipelines" / "orders" / "b").exists()


def test_a_second_run_overwrites_in_place(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _project(tmp_path)
    assert _tokenize(root, monkeypatch, "--out-dir", "b", "--vault", "v.db").exit_code == EXIT_OK
    before = _files(root)
    assert _tokenize(root, monkeypatch, "--out-dir", "b", "--vault", "v.db").exit_code == EXIT_OK
    assert _files(root) == before


def test_detokenize_reads_the_out_dir_file_by_the_suffix_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path)
    assert _tokenize(root, monkeypatch, "--out-dir", "b", "--vault", "v.db").exit_code == EXIT_OK
    result = runner.invoke(
        app, ["detokenize", "orders", "b/tok.csv", "--vault", "v.db"], catch_exceptions=False
    )
    assert result.exit_code == EXIT_OK, result.output
    got = pd.read_csv(root / "b" / "tok.detokenized.csv", dtype=str)
    assert got["email"].tolist() == EMAILS


def test_a_vault_that_aliases_a_target_is_refused_before_any_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path)
    _no_source_read(monkeypatch)
    before = _files(root)
    result = _tokenize(root, monkeypatch, "--out-dir", "b", "--vault", "b/tok.csv")
    assert result.exit_code == EXIT_USAGE
    assert "layout.output_path_collision" in result.output
    assert _files(root) == before


def test_a_target_escaping_dir_is_refused_before_any_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path, target="../x.csv")
    _no_source_read(monkeypatch)
    before = _files(root)
    result = _tokenize(root, monkeypatch, "--out-dir", "b", "--vault", "v.db")
    assert result.exit_code == EXIT_USAGE
    assert "layout.output_path_escapes" in result.output
    assert _files(root) == before


def test_a_dir_that_is_a_file_is_refused_and_nothing_is_made(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path)
    (root / "b").write_text("x", encoding="utf-8")
    _no_source_read(monkeypatch)
    before = _files(root)
    result = _tokenize(root, monkeypatch, "--out-dir", "b", "--vault", "v.db")
    assert result.exit_code == EXIT_USAGE
    assert "layout.output_dir_unusable" in result.output
    assert _files(root) == before


def test_without_out_dir_a_run_folder_is_still_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path)
    assert _tokenize(root, monkeypatch, "--vault", "v.db").exit_code == EXIT_OK
    assert list((root / "out" / "orders").glob("*/tok.csv"))


def test_a_refusal_carries_its_code_and_every_finding_in_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    root = _project(tmp_path)
    result = _tokenize(root, monkeypatch, "--out-dir", "b", "--vault", "b/tok.csv", "--json")
    assert result.exit_code == EXIT_USAGE
    doc = json.loads(result.stdout)
    assert doc["code"] == "layout.output_path_collision"
    assert doc["error_kind"] == "validation"
    assert [m["code"] for m in doc["messages"]] == ["layout.output_path_collision"]
