"""AT-19: every top-level command and group in `decoy --help` sits in a named help panel.

A new command added with no `rich_help_panel` lands in Typer's default "Commands" box, so a
user who looks for the generation path never sees it grouped. This reads the live Click tree
(hidden commands excluded) and fails on a command with no panel or a panel outside the
reviewed set. The self-test seeds a command with no panel and checks the walker reports it.
"""

from __future__ import annotations

import typer
import typer.main
from typer.testing import CliRunner

from decoy.__main__ import app

PANELS = frozenset({"Start", "Run", "Generate", "Mask", "Check and report", "Reference"})


def unpanelled(root: object) -> list[str]:
    """Visible top-level commands whose panel is missing or not a reviewed panel."""
    bad: list[str] = []
    for name, cmd in sorted(getattr(root, "commands", {}).items()):
        if getattr(cmd, "hidden", False):
            continue
        if getattr(cmd, "rich_help_panel", None) not in PANELS:
            bad.append(name)
    return bad


def test_every_visible_command_has_a_reviewed_panel() -> None:
    assert unpanelled(typer.main.get_command(app)) == []


def test_help_shows_a_generate_panel_with_fit() -> None:
    res = CliRunner().invoke(app, ["--help"], terminal_width=120)

    assert res.exit_code == 0, res.output
    lines = res.output.splitlines()
    start = next(i for i, ln in enumerate(lines) if "Generate" in ln and "╭" in ln)
    end = next(i for i in range(start, len(lines)) if "╰" in lines[i])
    assert any(" fit " in f" {ln} " for ln in lines[start:end]), "\n".join(lines[start:end])


def test_help_epilog_names_the_generation_path() -> None:
    res = CliRunner().invoke(app, ["--help"], terminal_width=160)

    flat = " ".join(res.output.split())
    assert "decoy fit" in flat and "decoy run" in flat
    assert "decoy report fidelity" in flat and "--generate" in flat


def test_seeded_command_without_a_panel_is_reported() -> None:
    seeded = typer.Typer()

    @seeded.command(name="paneled", rich_help_panel="Run")
    def _paneled() -> None: ...

    @seeded.command(name="loose")
    def _loose() -> None: ...

    assert unpanelled(typer.main.get_command(seeded)) == ["loose"]
