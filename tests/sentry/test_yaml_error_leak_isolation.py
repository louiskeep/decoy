"""Leak sentry: a YAML parse error must never echo the offending source line.

PyYAML's error text (and ``MarkedYAMLError.get_snippet()``) quotes the line it
choked on verbatim. Every CLI command that parses a config file before running
once interpolated ``str(exc)`` into its error message, so a malformed config
whose broken line held a secret leaked that secret to stdout, stderr, and the
``--json`` envelope. `decoy.cli._yaml_errors.sanitize_yaml_error` is the shared
fix; this sentry feeds each of those commands a malformed config carrying a
distinctive sentinel on the broken line and asserts the sentinel never appears
in any output stream.

Fail-before: on the pre-fix code each parametrized case leaked the sentinel.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()

# A distinctive marker on an unterminated YAML flow sequence: the `[` makes
# safe_load raise a YAMLError whose snippet quotes this whole line.
_SENTINEL = "YAMLLEAK_SENTINEL_" + "Z" * 12
_BAD_YAML = f"version: 1\napi_password: [{_SENTINEL}\n"
_WIDE_ENV = {"COLUMNS": "10000"}  # stop Rich truncating the sentinel mid-string


# Each builder takes the resolved fixture paths and returns the argv to run.
# Covers every command whose config-parse path routes through
# sanitize_yaml_error.
_COMMANDS: dict[str, Callable[[str, str, str, str], list[str]]] = {
    "validate": lambda cfg, src, out, vault: ["validate", cfg],
    "validate --json": lambda cfg, src, out, vault: ["validate", cfg, "--json"],
    "validate config": lambda cfg, src, out, vault: ["validate", "config", cfg, "--json"],
    "validate preflight": lambda cfg, src, out, vault: ["validate", "preflight", cfg, "--json"],
    "compile": lambda cfg, src, out, vault: ["compile", cfg, "--json"],
    "subset": lambda cfg, src, out, vault: ["subset", cfg, "--json"],
    "unmask": lambda cfg, src, out, vault: ["unmask", cfg, "--vault", vault, "--json"],
    "run": lambda cfg, src, out, vault: ["run", cfg, "--json"],
    "report fidelity": lambda cfg, src, out, vault: [
        "report",
        "fidelity",
        src,
        out,
        "--config",
        cfg,
        "--json",
    ],
    "report integrity": lambda cfg, src, out, vault: [
        "report",
        "integrity",
        out,
        "--source",
        src,
        "--config",
        cfg,
        "--json",
    ],
}


@pytest.mark.parametrize("label", list(_COMMANDS))
def test_yaml_parse_error_does_not_leak_source_line(label: str, tmp_path: Path) -> None:
    cfg_path = tmp_path / "bad.yaml"
    cfg_path.write_text(_BAD_YAML, encoding="utf-8")
    cfg = str(cfg_path)
    src = tmp_path / "src.csv"
    src.write_text("email\na@b.com\n", encoding="utf-8")
    out = tmp_path / "out.csv"
    out.write_text("email\nx@y.com\n", encoding="utf-8")
    vault = tmp_path / "vault.bin"  # need not exist; the config parse comes first

    argv = _COMMANDS[label](cfg, str(src), str(out), str(vault))
    result = runner.invoke(app, argv, env=_WIDE_ENV, catch_exceptions=False)
    combined = (result.stdout or "") + (result.stderr or "")
    assert _SENTINEL not in combined, (
        f"`decoy {' '.join(argv)}` leaked the config source line into its output:\n{combined}"
    )
