"""`decoy fit --fanout`: child counts per key kept in the snapshot (QA-FK-FANOUT C1, roadmap row 24h).

The block holds counts only, never a key value. Key values carry a ZZPATIENT marker the tests
look for.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_USAGE

runner = CliRunner()


def _flat(text: str) -> str:
    """Collapse Rich's soft wrapping so a phrase can be asserted whole."""
    return " ".join(text.split())


# --- QA-FK-FANOUT C1 (roadmap row 24h): `decoy fit --fanout` -------------------------------

# Child counts per patient: five with 1 visit, one with 2, one with 5, one with 8 (20 rows, 8 keys).
_FANOUT_DEGREES = [1, 1, 1, 1, 1, 2, 5, 8]
_FANOUT_KEYS = [f"ZZPATIENT{i:02d}" for i in range(len(_FANOUT_DEGREES))]


def _visits_csv(folder: Path) -> Path:
    src = folder / "visits.csv"
    ids = [k for k, d in zip(_FANOUT_KEYS, _FANOUT_DEGREES, strict=True) for _ in range(d)]
    pd.DataFrame({"patient_id": ids, "visit_no": range(len(ids))}).to_csv(src, index=False)
    return src


class TestFitFanout:
    def test_at_c1_block_line_and_no_key_value(self, tmp_path: Path) -> None:
        src = _visits_csv(tmp_path)
        out = tmp_path / "snapshot.json"
        result = runner.invoke(app, ["fit", str(src), "-o", str(out), "--fanout", "patient_id"])
        assert result.exit_code == 0, result.output
        snap = json.loads(out.read_text(encoding="utf-8"))
        block = snap["columns"]["patient_id"]["fanout"]
        assert block == {"rows": 20, "keys": 8, "degrees": [[1, 5], [2, 1], [5, 1], [8, 1]]}
        assert "fanout" not in snap["columns"]["visit_no"]
        assert "fan-out kept for patient_id: 8 keys, up to 8 rows per key" in _flat(result.stdout)
        assert "ZZPATIENT" not in json.dumps(block)
        assert "ZZPATIENT" not in result.stdout

    def test_at_c1_json_carries_fanout_columns(self, tmp_path: Path) -> None:
        src = _visits_csv(tmp_path)
        out = tmp_path / "snapshot.json"
        result = runner.invoke(
            app, ["fit", str(src), "-o", str(out), "--fanout", "patient_id", "--json"]
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert payload["fanout_columns"] == ["patient_id"]
        assert "ZZPATIENT" not in result.stdout

    def test_without_flag_snapshot_is_unchanged(self, tmp_path: Path) -> None:
        src = _visits_csv(tmp_path)
        plain, with_flag = tmp_path / "a.json", tmp_path / "b.json"
        assert runner.invoke(app, ["fit", str(src), "-o", str(plain)]).exit_code == 0
        assert (
            runner.invoke(
                app, ["fit", str(src), "-o", str(with_flag), "--fanout", "patient_id"]
            ).exit_code
            == 0
        )
        assert (
            "fanout" not in json.loads(plain.read_text(encoding="utf-8"))["columns"]["patient_id"]
        )
        result = runner.invoke(app, ["fit", str(src), "-o", str(plain), "--json"])
        assert json.loads(result.stdout)["fanout_columns"] == []

    def test_block_survives_on_a_withheld_sensitive_key_column(self, tmp_path: Path) -> None:
        ssns = [f"{100 + i:03d}-{20 + i:02d}-{1000 + i * 7:04d}" for i in range(6)]
        ids = [s for s, d in zip(ssns, [1, 1, 1, 2, 3, 4], strict=True) for _ in range(d)]
        src = tmp_path / "people.csv"
        pd.DataFrame({"ssn": ids, "n": range(len(ids))}).to_csv(src, index=False)
        out = tmp_path / "snapshot.json"
        result = runner.invoke(app, ["fit", str(src), "-o", str(out), "--fanout", "ssn"])
        assert result.exit_code == 0, result.output
        snap = json.loads(out.read_text(encoding="utf-8"))
        assert "ssn" in snap["redacted_columns"]
        assert snap["columns"]["ssn"]["fanout"] == {
            "rows": 12,
            "keys": 6,
            "degrees": [[1, 3], [2, 1], [3, 1], [4, 1]],
        }

    def test_at_c2_unknown_column_exits_usage_and_names_it(self, tmp_path: Path) -> None:
        src = _visits_csv(tmp_path)
        out = tmp_path / "snapshot.json"
        result = runner.invoke(app, ["fit", str(src), "-o", str(out), "--fanout", "nosuch"])
        assert result.exit_code == EXIT_USAGE
        assert "nosuch" in result.output
        assert not out.exists()

    def test_at_c2_fanout_with_epsilon_does_not_read_the_csv(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        src = _visits_csv(tmp_path)

        def _boom(*a: object, **k: object) -> None:
            raise AssertionError("the CSV was read")

        monkeypatch.setattr("decoy.cli.fit.read_fit_csv", _boom)
        monkeypatch.setattr("decoy.cli.fit.fit_exact_snapshot", _boom)
        result = runner.invoke(
            app,
            [
                "fit",
                str(src),
                "--fanout",
                "patient_id",
                "--epsilon",
                "1",
                "--delta",
                "1e-6",
                "--dp-text",
                "x",
            ],
        )
        assert result.exit_code == EXIT_USAGE, result.output
        assert "--fanout" in result.output
        assert "--epsilon" in result.output

    def test_at_c3_fit_validate_run_keeps_the_skew(self, tmp_path: Path) -> None:
        src = _visits_csv(tmp_path)
        snap = tmp_path / "visits.snapshot.json"
        fit = runner.invoke(app, ["fit", str(src), "-o", str(snap), "--fanout", "patient_id"])
        assert fit.exit_code == 0, fit.output
        cfg = {
            "version": 2,
            "global_settings": {"seed": 7},
            "sources": {},
            "tables": [
                {
                    "name": "patients",
                    "row_count": 10,
                    "generate_columns": [
                        {"name": "patient_id", "type": "sequence", "start": 1, "step": 1}
                    ],
                },
                {
                    "name": "visits",
                    "row_count": 20,
                    "generate_columns": [
                        {
                            "name": "patient_id",
                            "type": "reference",
                            "reference_table": "patients",
                            "reference_column": "patient_id",
                            "distribution": "fitted",
                            "snapshot_file": str(snap),
                        },
                        {"name": "visit_no", "type": "sequence", "start": 1, "step": 1},
                    ],
                },
            ],
            "targets": {
                t: {"type": "file", "format": "csv", "path": str(tmp_path / f"{t}.csv")}
                for t in ("patients", "visits")
            },
        }
        cfg_path = tmp_path / "gen.yaml"
        cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
        validate = runner.invoke(app, ["validate", str(cfg_path)])
        assert validate.exit_code == 0, validate.output
        run = runner.invoke(app, ["run", str(cfg_path)])
        assert run.exit_code == 0, run.output
        patients = pd.read_csv(tmp_path / "patients.csv")
        visits = pd.read_csv(tmp_path / "visits.csv")
        assert len(visits) == 20
        assert set(visits["patient_id"]) <= set(patients["patient_id"])
        degrees = visits["patient_id"].value_counts().reindex(patients["patient_id"], fill_value=0)
        assert sorted(degrees.tolist(), reverse=True) == [8, 5, 2, 1, 1, 1, 1, 1, 0, 0]
