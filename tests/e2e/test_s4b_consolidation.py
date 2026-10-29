"""E2E guard for the S4b `report` consolidation.

The run-artifact verbs live under `decoy report`; the old homes are gone:
  - the `evidence` and `vault` top-level groups,
  - `validate distribution` (validate is purely pre-run now),
  - `report compare` and `report summarize` (folded into `report diff`/`show`).
The output data checks (integrity, fidelity) live under `decoy post-scan`.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()


@pytest.mark.parametrize("sub", ["evidence", "vault"])
def test_removed_top_level_group_is_no_such_command(sub: str) -> None:
    result = runner.invoke(app, [sub], catch_exceptions=False)
    assert result.exit_code != 0
    combined = result.output + (result.stderr if hasattr(result, "stderr") else "")
    assert "no such command" in combined.lower()


@pytest.mark.parametrize(
    "argv",
    [
        ["report", "compare"],
        ["report", "summarize"],
    ],
)
def test_removed_report_subcommand_is_no_such_command(argv: list[str]) -> None:
    result = runner.invoke(app, argv, catch_exceptions=False)
    assert result.exit_code != 0
    combined = result.output + (result.stderr if hasattr(result, "stderr") else "")
    assert "no such command" in combined.lower()


def test_validate_distribution_is_not_a_subcommand() -> None:
    # `validate` uses a default-command group (unknown first token is treated
    # as a CONFIG path), so `validate distribution` is not "No such command"
    # but a bad-input error: there is no `distribution` subcommand, and
    # "distribution" is not a readable config file.
    result = runner.invoke(app, ["validate", "distribution"], catch_exceptions=False)
    assert result.exit_code != 0

    from decoy.cli.validate import validate_app

    sub_names = {c.name for c in validate_app.registered_commands}
    assert "distribution" not in sub_names
    assert {"config", "compile", "preflight"} <= sub_names


def test_report_surface_lists_the_five_verbs() -> None:
    result = runner.invoke(app, ["report", "--help"], catch_exceptions=False)
    assert result.exit_code == 0
    out = result.output
    for verb in ("show", "render", "verify", "diff", "vault"):
        assert verb in out, f"{verb} missing from `report --help`:\n{out}"
    for moved in ("fidelity", "integrity"):
        assert f"  {moved} " not in out, f"{moved} must live under `post-scan`:\n{out}"


def test_validate_help_has_no_distribution() -> None:
    result = runner.invoke(app, ["validate", "--help"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "distribution" not in result.output.lower()


def test_report_verbs_render_help() -> None:
    for verb in ("show", "render", "verify", "diff", "vault"):
        result = runner.invoke(app, ["report", verb, "--help"], catch_exceptions=False)
        assert result.exit_code == 0, f"`report {verb} --help` failed:\n{result.output}"


def test_post_scan_verbs_render_help() -> None:
    for verb in ("integrity", "fidelity"):
        result = runner.invoke(app, ["post-scan", verb, "--help"], catch_exceptions=False)
        assert result.exit_code == 0, f"`post-scan {verb} --help` failed:\n{result.output}"
