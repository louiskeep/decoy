"""`decoy init` for generation (GEN-CLI C2, AT-16 to AT-18 and AT-23).

`init --preset generate -o -` prints the YAML. `init <csv> --preset generate` fits a snapshot and
writes it with a config as one unit that rolls back whole.
"""

from __future__ import annotations

import errno
import json
import os
from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy import _atomic
from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_USAGE

runner = CliRunner()

posix = pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits")


def _flat(text: str) -> str:
    return " ".join(text.split())


def _people(folder: Path) -> Path:
    path = folder / "people.csv"
    pd.DataFrame(
        {
            "age": [20 + (i % 40) for i in range(120)],
            "score": [round(i * 0.37, 2) for i in range(120)],
            "city": ["Austin", "Boston", "Denver", "Eugene"] * 30,
        }
    ).to_csv(path, index=False)
    return path


def _listing(folder: Path) -> list[str]:
    return sorted(str(p.relative_to(folder)) for p in folder.rglob("*"))


# --- AT-16 -------------------------------------------------------------------


def test_preset_to_stdout_is_yaml_the_validator_accepts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    res = runner.invoke(app, ["init", "--preset", "generate", "-o", "-"])

    assert res.exit_code == 0, res.output
    assert not (tmp_path / "-").exists()
    cfg = tmp_path / "from_stdout.yaml"
    cfg.write_text(res.stdout, encoding="utf-8")
    assert isinstance(yaml.safe_load(res.stdout), dict)
    check = runner.invoke(app, ["validate", "config", str(cfg)])
    assert check.exit_code == 0, check.output


def test_stdout_carries_only_the_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    res = runner.invoke(app, ["init", "--preset", "generate", "-o", "-"])

    assert res.stdout.startswith(("#", "version")), res.stdout[:80]
    assert "wrote" not in res.stdout and "Next:" not in res.stdout


def test_stdout_with_json_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    res = runner.invoke(app, ["init", "--preset", "generate", "-o", "-", "--json"])

    assert res.exit_code == EXIT_USAGE, res.output
    assert not (tmp_path / "-").exists()
    assert _listing(tmp_path) == []


# --- AT-17 -------------------------------------------------------------------


def test_csv_scaffold_writes_snapshot_and_config_that_run_from_the_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = _people(tmp_path)
    monkeypatch.chdir(tmp_path)

    res = runner.invoke(app, ["init", str(src), "--preset", "generate", "-o", "gen/pipeline.yaml"])

    assert res.exit_code == 0, res.output
    assert (tmp_path / "gen" / "people.snapshot.json").is_file()
    cfg = yaml.safe_load((tmp_path / "gen" / "pipeline.yaml").read_text(encoding="utf-8"))
    (table,) = cfg["tables"]
    assert table["row_count"] == 120
    assert [c["name"] for c in table["generate_columns"]] == ["age", "score", "city"]
    assert {c["type"] for c in table["generate_columns"]} == {"statistical"}
    assert {c["snapshot_file"] for c in table["generate_columns"]} == {"people.snapshot.json"}
    (target,) = cfg["targets"].values()
    assert target["path"] == "people.synthetic.csv"

    run = runner.invoke(app, ["run", "gen/pipeline.yaml"])

    assert run.exit_code == 0, run.output
    out = pd.read_csv(tmp_path / "gen" / "people.synthetic.csv")
    assert list(out.columns) == ["age", "score", "city"] and len(out) == 120


@posix
def test_snapshot_is_private_and_config_is_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = _people(tmp_path)
    monkeypatch.chdir(tmp_path)

    res = runner.invoke(app, ["init", str(src), "--preset", "generate", "-o", "p.yaml"])

    assert res.exit_code == 0, res.output
    assert (tmp_path / "people.snapshot.json").stat().st_mode & 0o777 == 0o600


def test_csv_scaffold_json_envelope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = _people(tmp_path)
    monkeypatch.chdir(tmp_path)

    res = runner.invoke(app, ["init", str(src), "--preset", "generate", "-o", "p.yaml", "--json"])

    assert res.exit_code == 0, res.output
    payload = json.loads(res.stdout)
    assert payload["command"] == "init" and payload["status"] == "ok"
    assert payload["out"] == "p.yaml" and payload["snapshot"].endswith("people.snapshot.json")


# --- AT-18 -------------------------------------------------------------------


def test_csv_scaffold_to_stdout_is_refused_and_writes_no_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = _people(tmp_path)
    monkeypatch.chdir(tmp_path)
    before = _listing(tmp_path)

    res = runner.invoke(app, ["init", str(src), "--preset", "generate", "-o", "-"])

    assert res.exit_code == EXIT_USAGE, res.output
    assert _listing(tmp_path) == before


# --- AT-23 -------------------------------------------------------------------


def _scaffold(folder: Path, *extra: str, out: str = "p.yaml", input_text: str | None = None):
    return runner.invoke(
        app,
        [
            "init",
            str(folder / "people.csv"),
            "--preset",
            "generate",
            "-o",
            str(folder / out),
            *extra,
        ],
        input=input_text,
    )


def test_failed_validation_publishes_neither_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _people(tmp_path)
    from decoy.cli.gen import _scaffold as scaffold_module

    def refuse(*_a: object, **_k: object) -> None:
        raise scaffold_module.ScaffoldInvalid(["forced"])

    monkeypatch.setattr(scaffold_module, "_validate_pair", refuse)
    before = _listing(tmp_path)

    res = _scaffold(tmp_path)

    assert res.exit_code == EXIT_USAGE, res.output
    assert _listing(tmp_path) == before


def test_failed_validation_creates_no_new_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _people(tmp_path)
    from decoy.cli.gen import _scaffold as scaffold_module

    def refuse(*_a: object, **_k: object) -> None:
        raise scaffold_module.ScaffoldInvalid(["forced"])

    monkeypatch.setattr(scaffold_module, "_validate_pair", refuse)
    before = _listing(tmp_path)

    res = _scaffold(tmp_path, out="new/deep/p.yaml")

    assert res.exit_code == EXIT_USAGE
    assert _listing(tmp_path) == before


def _fail_second_replace(monkeypatch: pytest.MonkeyPatch) -> None:
    real = _atomic._publish
    calls = {"n": 0}

    def flaky(*args: object, **kwargs: object) -> bool:
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError(errno.EIO, "disk fault")
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(_atomic, "_publish", flaky)


@posix
def test_failure_on_the_second_replace_restores_both_old_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _people(tmp_path)
    snap, cfg = tmp_path / "people.snapshot.json", tmp_path / "p.yaml"
    snap.write_bytes(b"old snapshot")
    cfg.write_bytes(b"old config")
    snap.chmod(0o640)
    cfg.chmod(0o604)
    before = _listing(tmp_path)
    _fail_second_replace(monkeypatch)

    res = _scaffold(tmp_path, "--yes")

    assert res.exit_code == EXIT_USAGE, res.output
    assert (snap.read_bytes(), snap.stat().st_mode & 0o777) == (b"old snapshot", 0o640)
    assert (cfg.read_bytes(), cfg.stat().st_mode & 0o777) == (b"old config", 0o604)
    assert _listing(tmp_path) == before


def test_failure_on_the_second_replace_removes_new_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _people(tmp_path)
    before = _listing(tmp_path)
    _fail_second_replace(monkeypatch)

    res = _scaffold(tmp_path)

    assert res.exit_code == EXIT_USAGE, res.output
    assert _listing(tmp_path) == before


@pytest.mark.parametrize("existing", ["people.snapshot.json", "p.yaml"])
def test_an_existing_file_without_yes_is_refused_before_anything_is_staged(
    tmp_path: Path, existing: str
) -> None:
    _people(tmp_path)
    (tmp_path / existing).write_bytes(b"keep me")
    before = _listing(tmp_path)

    plain = _scaffold(tmp_path, "--json")
    declined = _scaffold(tmp_path, input_text="n\n")

    assert plain.exit_code == EXIT_USAGE and declined.exit_code == EXIT_USAGE
    assert _listing(tmp_path) == before
    assert (tmp_path / existing).read_bytes() == b"keep me"


def test_yes_overwrites_both_files(tmp_path: Path) -> None:
    _people(tmp_path)
    (tmp_path / "people.snapshot.json").write_bytes(b"old")
    (tmp_path / "p.yaml").write_bytes(b"old")

    res = _scaffold(tmp_path, "--yes")

    assert res.exit_code == 0, res.output
    assert json.loads((tmp_path / "people.snapshot.json").read_bytes())["columns"]
    assert yaml.safe_load((tmp_path / "p.yaml").read_bytes())["tables"]


def test_a_sensitive_categorical_column_fails_validation_and_writes_nothing(tmp_path: Path) -> None:
    pd.DataFrame(
        {
            "email": ["ann@example.com", "bo@example.com", "cy@example.com"] * 14,
            "age": list(range(42)),
        }
    ).to_csv(tmp_path / "people.csv", index=False)
    before = _listing(tmp_path)

    res = _scaffold(tmp_path)

    assert res.exit_code == EXIT_USAGE, res.output
    text = _flat(res.output)
    assert "does not validate" in text and "email" in text
    assert "ann@example.com" not in res.output
    assert _listing(tmp_path) == before
