"""S1 slice A: the deleted CLI surfaces are actually gone.

`jobs watch` and the `forge` console-script shim module were removed in the
CLI-redesign S1 foundations sprint
(docs/plans/2026-10-23-cli-redesign-s1-foundations.md). This locks the
removals in: the subcommand must resolve to a Typer "No such command" error
(non-zero exit), and the shim module must no longer be importable. The
renamed-away command surfaces are covered in `test_removed_commands_contract.py`.
"""

from __future__ import annotations

import importlib

import pytest
from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()


@pytest.mark.parametrize(
    "argv",
    [
        ["jobs", "watch"],
    ],
)
def test_removed_subcommand_resolves_to_no_such_command(argv: list[str]) -> None:
    result = runner.invoke(app, argv)
    assert result.exit_code != 0, f"{argv} unexpectedly succeeded"
    assert "No such command" in result.output, (
        f"{argv} did not produce a Typer 'No such command' error:\n{result.output}"
    )


def test_deprecated_forge_shim_module_is_gone() -> None:
    with pytest.raises(ImportError):
        importlib.import_module("decoy._deprecated")
