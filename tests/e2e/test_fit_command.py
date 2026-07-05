"""End-to-end tests for `decoy fit` + the statistical generate path (WS3).

`decoy fit` wraps the engine's `compute_distribution_snapshot`: it turns
a source CSV into the distribution-snapshot/v1 JSON artifact that
`type: statistical` generate columns consume. The flagship cell runs the
full loop: fit -> validate -> run -> synthetic output shaped like the
source.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_USAGE

runner = CliRunner()


def _source_csv(tmp_path: Path) -> Path:
    src = tmp_path / "source.csv"
    pd.DataFrame(
        {
            "amount": [10.5, 22.1, 9.9, 100.0, 55.2, 31.4, 18.8, 42.0] * 25,
            "state": (["CA"] * 5 + ["NY"] * 2 + ["TX"]) * 25,
            "joined": ["2024-01-05", "2024-03-02", "2025-06-01", "2023-12-25"] * 50,
        }
    ).to_csv(src, index=False)
    return src


class TestFit:
    def test_fit_writes_snapshot(self, tmp_path: Path) -> None:
        src = _source_csv(tmp_path)
        out = tmp_path / "snapshot.json"
        result = runner.invoke(app, ["fit", str(src), "--output", str(out)])
        assert result.exit_code == 0, result.output
        snap = json.loads(out.read_text(encoding="utf-8"))
        assert snap["schema_version"] == "distribution-snapshot/v1"
        assert snap["columns"]["amount"]["kind"] == "numeric"
        assert snap["columns"]["state"]["kind"] == "categorical"

    def test_parse_dates_flag(self, tmp_path: Path) -> None:
        src = _source_csv(tmp_path)
        out = tmp_path / "snapshot.json"
        result = runner.invoke(
            app, ["fit", str(src), "--output", str(out), "--parse-dates", "joined"]
        )
        assert result.exit_code == 0, result.output
        snap = json.loads(out.read_text(encoding="utf-8"))
        assert snap["columns"]["joined"]["kind"] == "datetime"

    def test_joint_flag_captures_contingency(self, tmp_path: Path) -> None:
        src = _source_csv(tmp_path)
        out = tmp_path / "snapshot.json"
        result = runner.invoke(
            app, ["fit", str(src), "--output", str(out), "--joint", "state,joined"]
        )
        assert result.exit_code == 0, result.output
        snap = json.loads(out.read_text(encoding="utf-8"))
        assert len(snap["joints"]) == 1
        assert snap["joints"][0]["columns"] == sorted(["state", "joined"])

    def test_bad_joint_spec_exits_usage(self, tmp_path: Path) -> None:
        src = _source_csv(tmp_path)
        result = runner.invoke(
            app,
            [
                "fit",
                str(src),
                "--output",
                str(tmp_path / "s.json"),
                "--joint",
                "only_one",
            ],
        )
        assert result.exit_code == EXIT_USAGE

    def test_default_output_path(self, tmp_path: Path) -> None:
        src = _source_csv(tmp_path)
        result = runner.invoke(app, ["fit", str(src)])
        assert result.exit_code == 0, result.output
        assert (tmp_path / "source.snapshot.json").exists()


class TestFitEpsilon:
    def test_epsilon_stamps_dp_metadata_and_removes_moments(
        self, tmp_path: Path
    ) -> None:
        src = _source_csv(tmp_path)
        out = tmp_path / "snapshot.json"
        result = runner.invoke(
            app, ["fit", str(src), "--output", str(out), "--epsilon", "1.0"]
        )
        assert result.exit_code == 0, result.output
        snap = json.loads(out.read_text(encoding="utf-8"))
        assert snap["dp"] == {
            "epsilon": 1.0,
            "mechanism": "laplace",
            "sensitivity": 1,
            "adjacency": "add-remove-one-row",
            "scope": "per-column-histogram",
        }
        assert snap["schema_version"] == "distribution-snapshot/v1"
        assert snap["columns"]["amount"]["stats"]["quantiles"] == {}

    def test_epsilon_with_joint_exits_usage(self, tmp_path: Path) -> None:
        src = _source_csv(tmp_path)
        result = runner.invoke(
            app, ["fit", str(src), "--epsilon", "1.0", "--joint", "state,joined"]
        )
        assert result.exit_code == EXIT_USAGE
        assert "composition" in result.output

    def test_invalid_epsilon_exits_usage(self, tmp_path: Path) -> None:
        src = _source_csv(tmp_path)
        result = runner.invoke(app, ["fit", str(src), "--epsilon", "0"])
        assert result.exit_code == EXIT_USAGE
        assert "dp_epsilon_invalid" in result.output


class TestFitGenerateLoop:
    def test_fit_then_generate(self, tmp_path: Path) -> None:
        src = _source_csv(tmp_path)
        snap_path = tmp_path / "snapshot.json"
        assert (
            runner.invoke(app, ["fit", str(src), "--output", str(snap_path)]).exit_code
            == 0
        )

        cfg = {
            "version": 1,
            "global_settings": {"seed": 42},
            "tables": [
                {
                    "name": "synthetic",
                    "row_count": 50,
                    "generate_columns": [
                        {
                            "name": "amount",
                            "type": "statistical",
                            "snapshot_file": str(snap_path),
                        },
                        {
                            "name": "state",
                            "type": "statistical",
                            "snapshot_file": str(snap_path),
                            "allow_real_categories": True,
                        },
                    ],
                }
            ],
            "targets": {
                "synthetic": {
                    "type": "file",
                    "format": "csv",
                    "path": str(tmp_path / "synthetic.csv"),
                }
            },
        }
        cfg_path = tmp_path / "gen.yaml"
        cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

        assert runner.invoke(app, ["validate", "config", str(cfg_path)]).exit_code == 0
        result = runner.invoke(app, ["run", str(cfg_path)])
        assert result.exit_code == 0, result.output
        out = pd.read_csv(tmp_path / "synthetic.csv")
        assert len(out) == 50
        assert set(out["state"].unique()) <= {"CA", "NY", "TX"}
        assert out["amount"].between(9.9, 100.0).all()

    def test_validate_rejects_missing_snapshot(self, tmp_path: Path) -> None:
        cfg = {
            "version": 1,
            "global_settings": {"seed": 42},
            "tables": [
                {
                    "name": "synthetic",
                    "row_count": 5,
                    "generate_columns": [
                        {
                            "name": "amount",
                            "type": "statistical",
                            "snapshot_file": str(tmp_path / "missing.json"),
                        }
                    ],
                }
            ],
            "targets": {
                "synthetic": {
                    "type": "file",
                    "format": "csv",
                    "path": str(tmp_path / "out.csv"),
                }
            },
        }
        cfg_path = tmp_path / "gen.yaml"
        cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
        result = runner.invoke(app, ["validate", "config", str(cfg_path)])
        assert result.exit_code == EXIT_USAGE
        assert "statistical_snapshot_unreadable" in result.output
