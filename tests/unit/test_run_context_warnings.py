"""`RunContext.add_cli_warning` is the one way to record a CLI warning, and its codes are closed."""

from __future__ import annotations

import pytest

from decoy.cli.run._context import CLI_WARNING_CODES, RunContext


def _ctx() -> RunContext:
    # The warning list needs no run state, so skip the option-heavy constructor.
    return object.__new__(RunContext)


def test_unknown_code_is_refused() -> None:
    ctx = _ctx()
    ctx._cli_warnings = []
    with pytest.raises(ValueError, match="unknown CLI warning code"):
        ctx.add_cli_warning("not_a_registered_code", "message")
    assert ctx._cli_warnings == []


def test_known_code_is_recorded() -> None:
    ctx = _ctx()
    ctx._cli_warnings = []
    code = next(iter(CLI_WARNING_CODES))
    ctx.add_cli_warning(code, "message")
    assert ctx._cli_warnings == [{"code": code, "message": "message"}]
