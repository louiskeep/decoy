"""Distribution-integrity QA report items (row 24e, slice C1).

A correct hash and faker masking failed `report fidelity --mode fail`, a joint across a hashed id
showed 0.000, `report integrity` printed no "same as source" rate and said a column was "not
configured to be masked" when no config was given, and a generate-only relationship needed a
namespace nothing used.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_FINDINGS
from tests.csv_sources import csv_source

runner = CliRunner()

_NOTE = (
    "Columns marked intended were masked with a strategy that replaces values, "
    "so a low score there is expected."
)


def _flat(text: str) -> str:
    return " ".join(text.split())


def _masked_pair(tmp_path: Path) -> tuple[Path, Path, Path]:
    n = 60
    src = tmp_path / "patients.csv"
    out = tmp_path / "out.csv"
    pd.DataFrame(
        {
            "patient_id": [f"P{i:04d}" for i in range(n)],
            "full_name": [f"Real Name {i}" for i in range(n)],
            "diagnosis": ["flu", "cold", "asthma"] * (n // 3),
        }
    ).to_csv(src, index=False)
    pd.DataFrame(
        {
            "patient_id": [f"h{i:08x}" for i in range(n)],
            "full_name": [f"Fake Person {i}" for i in range(n)],
            "diagnosis": ["flu", "cold", "asthma"] * (n // 3),
        }
    ).to_csv(out, index=False)
    cfg = {
        "version": 2,
        "global_settings": {"seed": 1},
        "sources": {"patients": csv_source(src)},
        "tables": [
            {
                "name": "patients",
                "columns": [
                    {"name": "patient_id", "strategy": "hash"},
                    {"name": "full_name", "strategy": "faker"},
                    {"name": "diagnosis", "strategy": "passthrough"},
                ],
            }
        ],
        "targets": {"patients": {"type": "file", "format": "csv", "path": str(out)}},
    }
    cfg_path = tmp_path / "mask.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return src, out, cfg_path


def _fidelity(src: Path, out: Path, *flags: str):
    args = ["report", "fidelity", str(src), str(out), *flags]
    human = runner.invoke(app, args, env={"COLUMNS": "200"})
    machine = runner.invoke(app, [*args, "--json"])
    return human, json.loads(machine.stdout)


# --- AT-C1.2: intended columns do not fail a correct masking ----------------------------


def test_correct_hash_and_faker_masking_passes_fail_mode(tmp_path: Path) -> None:
    src, out, cfg = _masked_pair(tmp_path)

    human, payload = _fidelity(src, out, "--config", str(cfg), "--mode", "fail")

    assert human.exit_code == 0, human.output
    assert payload["policy"]["violations"] == []
    assert payload["policy"]["intended_columns"] == ["full_name", "patient_id"]
    text = _flat(human.stdout)
    assert text.count(_NOTE) == 1
    rows = [line for line in human.stdout.splitlines() if "intended" in line.split()]
    assert {r.split()[0] for r in rows} >= {"patient_id", "full_name"}


def test_no_note_when_nothing_is_intended(tmp_path: Path) -> None:
    src, out, _ = _masked_pair(tmp_path)

    human, payload = _fidelity(src, out)

    assert payload["policy"]["intended_columns"] == []
    assert _NOTE not in _flat(human.stdout)


# --- AT-C1.3: a joint that names an intended column ---------------------------------------


def test_joint_naming_an_intended_column_prints_intended(tmp_path: Path) -> None:
    src, out, cfg = _masked_pair(tmp_path)

    human, payload = _fidelity(
        src, out, "--config", str(cfg), "--mode", "fail", "--joint", "patient_id,diagnosis"
    )

    assert human.exit_code == 0, human.output
    assert payload["policy"]["intended_joints"] == [["diagnosis", "patient_id"]]
    line = next(x for x in human.stdout.splitlines() if "diagnosisxpatient_id" in x)
    assert "intended" in line
    assert "0.000" not in line


# --- AT-C1.8: aggregates still count intended columns -------------------------------------


def test_min_grade_still_fails_a_correct_hash_masking(tmp_path: Path) -> None:
    src, out, cfg = _masked_pair(tmp_path)

    human, _ = _fidelity(src, out, "--config", str(cfg), "--mode", "fail", "--min-grade", "A")

    assert human.exit_code == EXIT_FINDINGS, human.output


def test_min_grade_help_says_intended_columns_count() -> None:
    result = runner.invoke(app, ["report", "fidelity", "--help"], env={"COLUMNS": "200"})
    assert "Intended columns count in the grade" in _flat(result.output)


# --- AT-C1.4 / AT-C1.5: integrity ---------------------------------------------------------


def _leaky_pair(tmp_path: Path) -> tuple[Path, Path]:
    src = tmp_path / "src.csv"
    masked = tmp_path / "masked.csv"
    rows = {"email": [f"user{i}@example.com" for i in range(30)]}
    pd.DataFrame(rows).to_csv(src, index=False)
    pd.DataFrame(rows).to_csv(masked, index=False)
    return src, masked


def test_integrity_table_shows_same_as_source_rate(tmp_path: Path) -> None:
    src, masked = _leaky_pair(tmp_path)
    args = ["report", "integrity", str(masked), "--source", str(src)]
    findings = json.loads(runner.invoke(app, [*args, "--json"]).stdout)["report"]["residual_pii"]
    assert findings

    human = runner.invoke(app, args, env={"COLUMNS": "10000"})

    assert "Same as source" in human.stdout
    for f in findings:
        rate = f.get("source_identity_rate")
        shown = "-" if rate is None else f"{rate:.2f}"
        row = next(x for x in human.stdout.splitlines() if f["column"] in x.split())
        assert shown in row.split(), row


def test_integrity_without_config_never_says_not_configured(tmp_path: Path) -> None:
    src, masked = _leaky_pair(tmp_path)

    human = runner.invoke(
        app,
        ["report", "integrity", str(masked), "--source", str(src)],
        env={"COLUMNS": "10000"},
    )

    assert human.exit_code == EXIT_FINDINGS, human.output
    assert "not configured to be masked" not in _flat(human.stdout)


# --- AT-C1.1 (GATE-12): generate-only relationship needs no namespace ---------------------


def _generate_fk_config(tmp_path: Path) -> Path:
    cfg = {
        "version": 2,
        "global_settings": {"seed": 7},
        "sources": {},
        "tables": [
            {
                "name": "patients",
                "row_count": 20,
                "generate_columns": [{"name": "patient_id", "type": "sequence", "start": 1}],
            },
            {
                "name": "visits",
                "row_count": 50,
                "generate_columns": [
                    {"name": "visit_id", "type": "sequence", "start": 1},
                    {
                        "name": "patient_id",
                        "type": "reference",
                        "reference_table": "patients",
                        "reference_column": "patient_id",
                    },
                ],
            },
        ],
        "relationships": [
            {
                "parent": {"table": "patients", "columns": ["patient_id"]},
                "children": [{"table": "visits", "columns": ["patient_id"]}],
                "orphan_policy": "preserve",
            }
        ],
        "targets": {
            "patients": {"type": "file", "format": "csv", "path": "./patients.csv"},
            "visits": {"type": "file", "format": "csv", "path": "./visits.csv"},
        },
    }
    path = tmp_path / "pipeline.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def test_generate_only_relationship_validates_and_runs(tmp_path: Path) -> None:
    cfg = _generate_fk_config(tmp_path)

    validated = runner.invoke(app, ["validate", str(cfg)])
    assert validated.exit_code == 0, validated.output
    assert "namespace_missing" not in validated.output

    ran = runner.invoke(app, ["run", str(cfg), "--quiet"])
    assert ran.exit_code == 0, ran.output
    patients = pd.read_csv(next(tmp_path.rglob("patients.csv")))
    visits = pd.read_csv(next(tmp_path.rglob("visits.csv")))
    assert len(visits) == 50
    assert set(visits["patient_id"]) <= set(patients["patient_id"])
