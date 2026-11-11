"""The `condition_on` joint cell cap and its two warnings (GEN-COND-CAP C1, roadmap row 24w).

A joint keeps its 25 largest cells by default. `decoy fit` now says when that cap cut
combinations and takes `--joint-max-cells` to raise it, and `decoy run` says when a conditional
column drew rows for a parent value with no kept combination. Values never show in the text:
every parent and child label carries a SENTP or SENTK marker the tests look for.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner, Result

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_OK, EXIT_USAGE

runner = CliRunner()
_WIDE = {"COLUMNS": "10000"}
_MARKERS = ("SENTP", "SENTK")
# Parent i's weight; each weight unit is 60 rows, 6,000 rows in all.
_PARENT_WEIGHTS = (20, 15, 12, 10, 9, 8, 7, 6, 5, 4, 3, 1)
_UNSEEN_PARENT = "SENTP12"


def _cond_rows() -> tuple[list[str], list[str]]:
    """36 (parent, kid) pairs with no RNG: at a cap of 25, SENTP12 keeps no cell."""
    parents: list[str] = []
    kids: list[str] = []
    for i, weight in enumerate(_PARENT_WEIGHTS, start=1):
        for j, share in enumerate((6, 3, 1)):
            count = weight * 60 * share // 10
            parents += [f"SENTP{i:02d}"] * count
            kids += [f"SENTK{(i + j) % 6 + 1}"] * count
    return parents, kids


def _cond_csv(folder: Path) -> Path:
    parents, kids = _cond_rows()
    path = folder / "cond.csv"
    pd.DataFrame({"parent": parents, "kid": kids}).to_csv(path, index=False)
    return path


def _fit(folder: Path, *extra: str) -> tuple[Result, Path]:
    out = folder / "cond.snapshot.json"
    result = runner.invoke(app, ["fit", str(_cond_csv(folder)), "-o", str(out), *extra], env=_WIDE)
    return result, out


def _stderr(result: Result) -> str:
    try:
        return result.stderr
    except ValueError:
        return ""


def _flat(text: str) -> str:
    return " ".join(text.split())


def _no_markers(*texts: str) -> None:
    for text in texts:
        assert not any(m in text for m in _MARKERS), "a cell value reached the output"


# --- AT-9: the fit warning ------------------------------------------------------------


def test_at9_default_cap_warns_once_on_stderr(tmp_path: Path) -> None:
    result, out = _fit(tmp_path, "--joint", "parent,kid")
    assert result.exit_code == EXIT_OK, result.output
    err = _flat(_stderr(result))
    assert err.count("warning:") == 1, err
    # The snapshot stores a pair sorted by name, and the line names it that way.
    assert "joint kid x parent: 36 combinations, 25 kept; 11 dropped by the cell cap" in err
    assert "366 rows in all fall outside the kept ones" in err
    assert "Raise --joint-max-cells (at most 1000) to keep the 11." in err
    assert out.exists()
    _no_markers(result.stdout, _stderr(result))


def test_at9_default_cap_warning_in_json(tmp_path: Path) -> None:
    result, _ = _fit(tmp_path, "--joint", "parent,kid", "--json")
    assert result.exit_code == EXIT_OK, result.output
    warnings = json.loads(result.stdout)["warnings"]
    assert [w["code"] for w in warnings] == ["fit_joint_cells_truncated"]
    assert set(warnings[0]) == {"code", "message", "detail"}
    detail = warnings[0]["detail"]
    assert detail["cell_count"] == 36 and detail["cells_kept"] == 25
    assert detail["cap_dropped"] == 11 and detail["policy_dropped"] == 0
    assert detail["other_count"] == 366
    _no_markers(result.stdout)


def test_at9_quiet_prints_no_warning(tmp_path: Path) -> None:
    result, _ = _fit(tmp_path, "--joint", "parent,kid", "--quiet")
    assert result.exit_code == EXIT_OK, result.output
    assert "warning:" not in _stderr(result)


def test_at9_raised_cap_keeps_every_cell_and_warns_nothing(tmp_path: Path) -> None:
    human, out = _fit(tmp_path, "--joint", "parent,kid", "--joint-max-cells", "36")
    assert human.exit_code == EXIT_OK, human.output
    assert "warning:" not in _stderr(human)
    joint = json.loads(out.read_text(encoding="utf-8"))["joints"][0]
    assert len(joint["cells"]) == 36 and joint["other_count"] == 0
    machine, _ = _fit(tmp_path, "--joint", "parent,kid", "--joint-max-cells", "36", "--json")
    assert machine.exit_code == EXIT_OK, machine.output
    assert json.loads(machine.stdout)["warnings"] == []


# --- AT-10: usage order and the bound -----------------------------------------------


def _refused(tmp_path: Path, code: str, *args: str) -> None:
    result, out = _fit(tmp_path, *args, "--json")
    assert result.exit_code == EXIT_USAGE, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "error" and payload["code"] == code, payload
    assert not out.exists()


def test_at10_zero_cap_is_refused(tmp_path: Path) -> None:
    _refused(
        tmp_path, "contingency_top_k_invalid", "--joint", "parent,kid", "--joint-max-cells", "0"
    )


def test_at10_cap_over_the_bound_is_refused(tmp_path: Path) -> None:
    args = ("--joint", "parent,kid", "--joint-max-cells", "1001")
    _refused(tmp_path, "contingency_top_k_invalid", *args)


def test_at10_non_number_cap_is_refused(tmp_path: Path) -> None:
    args = ("--joint", "parent,kid", "--joint-max-cells", "many")
    _refused(tmp_path, "contingency_top_k_invalid", *args)


@pytest.mark.parametrize("bad", ["1_000", "+30", "\u0663\u0666"])
def test_at10_non_ascii_digit_forms_are_refused(tmp_path: Path, bad: str) -> None:
    _refused(
        tmp_path, "contingency_top_k_invalid", "--joint", "parent,kid", "--joint-max-cells", bad
    )


def test_at10_cap_needs_joint(tmp_path: Path) -> None:
    _refused(tmp_path, "fit_joint_max_cells_needs_joint", "--joint-max-cells", "36")


def test_at10_cap_needs_joint_also_with_epsilon(tmp_path: Path) -> None:
    args = ("--joint-max-cells", "36", "--epsilon", "1.0", "--delta", "1e-6", "--dp-text", "kid")
    _refused(tmp_path, "fit_joint_max_cells_needs_joint", *args)


def test_at10_joint_with_epsilon_keeps_its_refusal(tmp_path: Path) -> None:
    args = ("--joint", "parent,kid", "--joint-max-cells", "36", "--epsilon", "1.0")
    _refused(tmp_path, "dp_mode_joint_unsupported", *args, "--delta", "1e-6", "--dp-text", "kid")


def test_at10_human_error_names_the_code(tmp_path: Path) -> None:
    result, _ = _fit(tmp_path, "--joint", "parent,kid", "--joint-max-cells", "0")
    assert result.exit_code == EXIT_USAGE
    assert "contingency_top_k_invalid" in _flat(_stderr(result))
    assert "Traceback" not in result.output


# --- AT-10b: a raised cap on a column that is not a plain category -------------------

_NUM_ROWS = 200


def _numeric_fit(folder: Path, *extra: str) -> tuple[Result, Path]:
    src = folder / "numeric.csv"
    frame = pd.DataFrame(
        {
            "amount": [i * 1.37 for i in range(_NUM_ROWS)],
            "kid": [f"SENTK{i % 3}" for i in range(_NUM_ROWS)],
        }
    )
    frame.to_csv(src, index=False)
    out = folder / "numeric.snapshot.json"
    args = ["fit", str(src), "-o", str(out), "--joint", "amount,kid", "--joint-max-cells", "26"]
    return runner.invoke(app, [*args, *extra], env=_WIDE), out


def test_at10_raised_cap_on_a_numeric_column_is_refused_in_json(tmp_path: Path) -> None:
    result, out = _numeric_fit(tmp_path, "--json")
    assert result.exit_code == EXIT_USAGE, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "error" and payload["code"] == "contingency_top_k_kind_unsupported"
    assert not out.exists()


def test_at10_raised_cap_on_a_numeric_column_names_the_code_in_human_mode(tmp_path: Path) -> None:
    result, out = _numeric_fit(tmp_path)
    assert result.exit_code == EXIT_USAGE, result.output
    assert "contingency_top_k_kind_unsupported" in _flat(_stderr(result))
    assert "Traceback" not in result.output
    assert not out.exists()


def test_at10_include_values_allows_the_raised_cap_on_a_numeric_column(tmp_path: Path) -> None:
    result, out = _numeric_fit(tmp_path, "--include-values")
    assert result.exit_code == EXIT_OK, result.output
    assert out.exists()


# --- AT-11: the generation warning in `decoy run` -------------------------------------


def _run_config(folder: Path, snapshot: Path) -> Path:
    def column(name: str, **extra: Any) -> dict[str, Any]:
        return {
            "name": name,
            "type": "statistical",
            "snapshot_file": str(snapshot),
            "allow_real_categories": True,
            **extra,
        }

    cfg = {
        "version": 2,
        "global_settings": {"seed": 42},
        "tables": [
            {
                "name": "synthetic",
                "row_count": 6000,
                "generate_columns": [column("parent"), column("kid", condition_on="parent")],
            }
        ],
        "targets": {
            "synthetic": {"type": "file", "format": "csv", "path": str(folder / "synthetic.csv")}
        },
    }
    path = folder / "gen.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _default_snapshot_config(folder: Path) -> Path:
    result, snap = _fit(folder, "--joint", "parent,kid")
    assert result.exit_code == EXIT_OK, result.output
    return _run_config(folder, snap)


def test_at11_run_summary_names_the_fallback(tmp_path: Path) -> None:
    cfg = _default_snapshot_config(tmp_path)
    result = runner.invoke(app, ["run", str(cfg)], env=_WIDE)
    assert result.exit_code == EXIT_OK, result.output
    rows = int((pd.read_csv(tmp_path / "synthetic.csv")["parent"] == _UNSEEN_PARENT).sum())
    assert rows > 0
    text = _flat(result.stdout)
    assert "Warnings 1" in text
    assert (
        f"table synthetic, column kid (condition_on parent): {rows} of 6000 rows "
        "(0 of them with an empty parent) had one of 1 parent values with no fitted "
        "combination and drew from the column's overall counts."
    ) in text
    _no_markers(result.stdout, _stderr(result))


def test_at11_run_json_carries_the_fallback(tmp_path: Path) -> None:
    cfg = _default_snapshot_config(tmp_path)
    result = runner.invoke(app, ["run", str(cfg), "--json"], env=_WIDE)
    assert result.exit_code == EXIT_OK, result.output
    warnings = json.loads(result.stdout)["warnings"]
    assert [w["code"] for w in warnings] == ["generation_condition_parent_unseen"]
    assert "drew from the column's overall counts" in warnings[0]["message"]
    assert warnings[0]["detail"]["parent_values"] == 1
    _no_markers(result.stdout)


# --- AT-15: a withheld joint never gets a truncation warning --------------------------

# Eight repeating SSN-shaped strings (not real numbers): the profiler flags the column, and with
# five kids the pair has 40 combinations, more than the default cap.
_ROWS = 96
_SSNS = [f"{100 + i % 8:03d}-{20 + i % 8:02d}-{1000 + (i % 8) * 7:04d}" for i in range(_ROWS)]
_KIDS = [f"SENTK{i % 5 + 1}" for i in range(_ROWS)]


def _flagged_fit(folder: Path, *extra: str) -> tuple[Result, dict[str, Any]]:
    src = folder / "flagged.csv"
    pd.DataFrame({"ssn": _SSNS, "kid": _KIDS}).to_csv(src, index=False)
    out = folder / "flagged.snapshot.json"
    result = runner.invoke(
        app, ["fit", str(src), "-o", str(out), "--joint", "ssn,kid", *extra], env=_WIDE
    )
    assert result.exit_code == EXIT_OK, result.output
    return result, json.loads(out.read_text(encoding="utf-8"))


def test_at15_withheld_joint_at_the_raised_cap(tmp_path: Path) -> None:
    result, doc = _flagged_fit(tmp_path, "--joint-max-cells", "1000")
    assert "ssn" in doc["redacted_columns"]
    assert doc["joints"][0]["cells"] == []
    assert "warning:" not in _stderr(result)
    assert not any(ssn in result.output for ssn in _SSNS)


def test_at15_withheld_joint_at_the_default_cap_in_json(tmp_path: Path) -> None:
    result, doc = _flagged_fit(tmp_path, "--json")
    assert doc["joints"][0]["cell_count"] > 25
    assert json.loads(result.stdout)["warnings"] == []
