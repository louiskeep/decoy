"""Generation runs a first-time user could not read or trust (GEN-CLI C1, roadmap row 24o).

One path rule (a relative YAML path reads from the config's folder), warnings in the run
summary and in `run --json`, the `--fidelity` refusal on a pipeline with no mask table, and the
seed-with-key warning.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_USAGE
from tests.csv_sources import csv_source
from tests.keyed_secret import TEST_MASK_SECRET_REF

pytestmark = pytest.mark.usefixtures("mask_secret")

runner = CliRunner()

_KEY = "ab" * 32
_FIDELITY_REFUSAL = (
    "--fidelity scores mask tables and this pipeline has none. Score generated tables with: "
    "decoy report fidelity <source.csv> <synthetic.csv> --generate"
)


def _flat(text: str) -> str:
    return " ".join(text.split())


def _source_csv(folder: Path) -> Path:
    path = folder / "source.csv"
    pd.DataFrame(
        {
            "amount": [float(i % 50) + 0.5 for i in range(200)],
            "state": ["CA", "NY", "TX", "WA"] * 50,
        }
    ).to_csv(path, index=False)
    return path


def _snapshot(folder: Path) -> Path:
    snap = folder / "snap.json"
    res = runner.invoke(app, ["fit", str(_source_csv(folder)), "--output", str(snap)])
    assert res.exit_code == 0, res.output
    return snap


def _generate_table(snapshot_file: str) -> dict:
    return {
        "name": "synthetic",
        "row_count": 60,
        "generate_columns": [
            {"name": "amount", "type": "statistical", "snapshot_file": snapshot_file},
            {
                "name": "state",
                "type": "statistical",
                "snapshot_file": snapshot_file,
                "allow_real_categories": True,
            },
        ],
    }


def _generate_config(folder: Path, *, snapshot_file: str = "snap.json", **settings: object) -> Path:
    cfg = {
        "version": 2,
        "global_settings": {"seed": 42, **settings},
        "tables": [_generate_table(snapshot_file)],
        "targets": {"synthetic": {"type": "file", "format": "csv", "path": "synthetic.csv"}},
    }
    path = folder / "gen.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _mixed_config(folder: Path, *, seed: int = 42) -> Path:
    pd.DataFrame({"name": ["a", "b", "c", "d", "e", "f"]}).to_csv(
        folder / "people.csv", index=False
    )
    cfg = {
        "version": 2,
        "global_settings": {"seed": seed, "mask_secret_ref": TEST_MASK_SECRET_REF},
        "sources": {"people": csv_source("people.csv")},
        "tables": [
            {"name": "people", "columns": [{"name": "name", "strategy": "shuffle"}]},
            _generate_table("snap.json"),
        ],
        "targets": {
            "people": {"type": "file", "format": "csv", "path": "people_out.csv"},
            "synthetic": {"type": "file", "format": "csv", "path": "synthetic.csv"},
        },
    }
    path = folder / "mixed.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _mask_config(folder: Path, *, seed: int = 42) -> Path:
    pd.DataFrame({"name": ["a", "b", "c"]}).to_csv(folder / "people.csv", index=False)
    cfg = {
        "version": 2,
        "global_settings": {"seed": seed, "mask_secret_ref": TEST_MASK_SECRET_REF},
        "sources": {"people": csv_source("people.csv")},
        "tables": [{"name": "people", "columns": [{"name": "name", "strategy": "shuffle"}]}],
        "targets": {"people": {"type": "file", "format": "csv", "path": "people_out.csv"}},
    }
    path = folder / "mask.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _keyed(*extra: str) -> list[str]:
    return ["--master-key", _KEY, "--key-label", "t", *extra]


# --- AT-1, AT-5: one path rule ------------------------------------------------


def test_run_from_another_folder_reads_the_snapshot_beside_the_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    _snapshot(a)
    cfg = _generate_config(a)

    monkeypatch.chdir(a)
    assert runner.invoke(app, ["run", str(cfg)]).exit_code == 0
    from_a = (a / "synthetic.csv").read_bytes()
    (a / "synthetic.csv").unlink()

    monkeypatch.chdir(b)
    res = runner.invoke(app, ["run", str(cfg)])

    assert res.exit_code == 0, res.output
    assert (a / "synthetic.csv").read_bytes() == from_a


def test_validate_and_ci_gate_agree_with_run_from_another_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    _snapshot(a)
    cfg = _generate_config(a)
    monkeypatch.chdir(b)

    for argv in (
        ["validate", "config", str(cfg)],
        ["validate", "compile", str(cfg), "--explain"],
        ["validate", "preflight", str(cfg)],
    ):
        res = runner.invoke(app, argv)
        assert res.exit_code == 0, (argv, res.output)


def test_unreadable_snapshot_names_the_config_folder_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    _snapshot(b)  # present in the working directory only
    cfg = _generate_config(a)
    monkeypatch.chdir(b)

    res = runner.invoke(app, ["run", str(cfg)])

    assert res.exit_code == EXIT_USAGE, res.output
    text = _flat(res.output)
    assert str(a / "snap.json") in text
    assert "config" in text


def test_column_names_file_reads_from_the_config_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "people.csv").write_text("x1\ny2\nz3\n", encoding="utf-8")
    (a / "names.txt").write_text("name\n", encoding="utf-8")
    src = csv_source("people.csv")
    src.pop("has_header")
    src.update({"has_header": False, "column_names_file": "names.txt"})
    cfg = {
        "version": 2,
        "global_settings": {"seed": 1, "mask_secret_ref": TEST_MASK_SECRET_REF},
        "sources": {"people": src},
        "tables": [{"name": "people", "columns": [{"name": "name", "strategy": "shuffle"}]}],
        "targets": {"people": {"type": "file", "format": "csv", "path": "out.csv"}},
    }
    path = a / "pipeline.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    monkeypatch.chdir(b)

    res = runner.invoke(app, ["run", str(path)])

    assert res.exit_code == 0, res.output
    assert list(pd.read_csv(a / "out.csv").columns) == ["name"]


# --- AT-9, AT-10: warnings and per-table lines ---------------------------------


def _weak_config(folder: Path) -> Path:
    _snapshot(folder)
    return _generate_config(folder, fidelity_warn_threshold=1.0)


def test_low_fidelity_shows_in_the_card_and_json(tmp_path: Path) -> None:
    cfg = _weak_config(tmp_path)

    human = runner.invoke(app, ["run", str(cfg)])
    machine = runner.invoke(app, ["run", str(cfg), "--json"])

    assert human.exit_code == 0 and machine.exit_code == 0, human.output
    text = _flat(human.stdout)
    assert "Warnings 1" in text
    assert "table synthetic:" in text and "fidelity_warn_threshold 1.00" in text
    warnings = json.loads(machine.stdout)["warnings"]
    assert [w["code"] for w in warnings] == ["generation_fidelity_below_threshold"]
    assert warnings[0]["table"] == "synthetic"
    assert set(warnings[0]) == {"code", "table", "column", "message", "detail"}


def test_warning_text_holds_no_cell_value(tmp_path: Path) -> None:
    cfg = _weak_config(tmp_path)
    res = runner.invoke(app, ["run", str(cfg), "--json"])
    blob = json.dumps(json.loads(res.stdout)["warnings"])
    source = pd.read_csv(tmp_path / "source.csv")
    for value in set(source["state"]):
        assert f'"{value}"' not in blob


def test_clean_run_has_an_empty_warnings_list(tmp_path: Path) -> None:
    _snapshot(tmp_path)
    cfg = _generate_config(tmp_path, fidelity_warn_threshold=0.0)

    machine = runner.invoke(app, ["run", str(cfg), "--json"])
    human = runner.invoke(app, ["run", str(cfg)])

    assert json.loads(machine.stdout)["warnings"] == []
    assert "Warnings" not in human.stdout


def test_human_run_lists_each_table_with_rows_and_file(tmp_path: Path) -> None:
    _snapshot(tmp_path)
    cfg = _generate_config(tmp_path, fidelity_warn_threshold=0.0)

    res = runner.invoke(app, ["run", str(cfg)])

    text = _flat(res.stdout)
    assert "synthetic 60 rows" in text
    assert "synthetic.csv" in text


# --- AT-11, AT-12: --fidelity -------------------------------------------------


def test_fidelity_on_a_generate_only_pipeline_is_refused_before_any_work(tmp_path: Path) -> None:
    _snapshot(tmp_path)
    cfg = _generate_config(tmp_path)

    res = runner.invoke(app, ["run", str(cfg), "--fidelity"])

    assert res.exit_code == EXIT_USAGE
    assert _FIDELITY_REFUSAL in _flat(res.output)
    assert not (tmp_path / "synthetic.csv").exists()


def test_fidelity_refusal_in_json_mode(tmp_path: Path) -> None:
    _snapshot(tmp_path)
    cfg = _generate_config(tmp_path)

    res = runner.invoke(app, ["run", str(cfg), "--fidelity", "--json"])

    assert res.exit_code == EXIT_USAGE
    assert json.loads(res.stdout)["error"] == _FIDELITY_REFUSAL


def test_fidelity_on_a_mixed_pipeline_reports_masks_then_points_at_report_fidelity(
    tmp_path: Path,
) -> None:
    _snapshot(tmp_path)
    cfg = _mixed_config(tmp_path)

    res = runner.invoke(app, ["run", str(cfg), "--fidelity"])

    assert res.exit_code == 0, res.output
    text = _flat(res.stdout)
    assert "Fidelity (quick inline check)" in text
    assert text.index("Fidelity (quick inline check)") < text.index("decoy report fidelity")
    assert "<source.csv> <synthetic.csv> --generate" in text


# --- AT-13: the seed and the master key ---------------------------------------


def test_seed_with_a_key_warns_for_generate_only(tmp_path: Path) -> None:
    _snapshot(tmp_path)
    cfg = _generate_config(tmp_path, fidelity_warn_threshold=0.0)

    keyed_only = runner.invoke(app, ["run", str(cfg), *_keyed(), "--json"])
    codes = [w["code"] for w in json.loads(keyed_only.stdout)["warnings"]]
    out_with_seed = (tmp_path / "synthetic.csv").read_bytes()

    assert keyed_only.exit_code == 0, keyed_only.output
    assert codes == ["seed_ignored_with_master_key"]
    assert (
        "not used for generated tables" in json.loads(keyed_only.stdout)["warnings"][0]["message"]
    )

    # The key decides generated bytes: another seed gives the same output.
    other = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    other["global_settings"]["seed"] = 7
    cfg.write_text(yaml.safe_dump(other), encoding="utf-8")
    (tmp_path / "synthetic.csv").unlink()
    res = runner.invoke(app, ["run", str(cfg), *_keyed(), "--json"])
    assert res.exit_code == 0, res.output
    assert (tmp_path / "synthetic.csv").read_bytes() == out_with_seed


def test_seed_with_a_key_warns_on_a_mixed_pipeline_and_masks_still_use_the_seed(
    tmp_path: Path,
) -> None:
    _snapshot(tmp_path)
    outputs = []
    for seed in (1, 2, 3, 4):
        cfg = _mixed_config(tmp_path, seed=seed)
        res = runner.invoke(app, ["run", str(cfg), *_keyed(), "--json"])
        assert res.exit_code == 0, res.output
        codes = [w["code"] for w in json.loads(res.stdout)["warnings"]]
        assert "seed_ignored_with_master_key" in codes
        outputs.append((tmp_path / "people_out.csv").read_bytes())
    assert len(set(outputs)) > 1


def test_no_seed_warning_without_a_key_or_on_mask_only(tmp_path: Path) -> None:
    _snapshot(tmp_path)
    cfg = _generate_config(tmp_path, fidelity_warn_threshold=0.0)
    no_key = runner.invoke(app, ["run", str(cfg), "--json"])
    assert json.loads(no_key.stdout)["warnings"] == []

    mask = _mask_config(tmp_path)
    keyed_mask = runner.invoke(app, ["run", str(mask), *_keyed(), "--json"])
    assert keyed_mask.exit_code == 0, keyed_mask.output
    assert json.loads(keyed_mask.stdout)["warnings"] == []


def test_master_key_help_says_the_seed_is_not_used_for_generation() -> None:
    res = runner.invoke(app, ["run", "--help"], terminal_width=200)
    assert "not used for generated tables" in re.sub(r"[│\s]+", " ", res.stdout)
