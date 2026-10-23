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
# Each builder takes (cfg, src, out) and returns argv. `cfg` is the malformed
# config; `src`/`out` stand in for any required CSV/masked/vault positionals so
# the command actually REACHES its config parse (a command that bails on a
# missing arg first would pass this sentry vacuously). Covers every config/
# policy parse site routed through sanitize_yaml_error, in text and JSON modes.
_COMMANDS: dict[str, Callable[[str, str, str], list[str]]] = {
    "validate (text)": lambda cfg, src, out: ["validate", cfg],
    "validate --json": lambda cfg, src, out: ["validate", cfg, "--json"],
    "validate config": lambda cfg, src, out: ["validate", "config", cfg, "--json"],
    "validate compile": lambda cfg, src, out: ["validate", "compile", cfg, "--json"],
    "validate preflight": lambda cfg, src, out: ["validate", "preflight", cfg, "--json"],
    "subset": lambda cfg, src, out: ["subset", cfg, "--dry-run", "--json"],
    "unmask": lambda cfg, src, out: ["unmask", cfg, out, "--json"],
    "run": lambda cfg, src, out: ["run", cfg, "--json"],
    "report fidelity --config": lambda cfg, src, out: [
        "report", "fidelity", src, out, "--config", cfg, "--json"
    ],
    "report fidelity --policy": lambda cfg, src, out: [
        "report", "fidelity", src, out, "--policy", cfg, "--json"
    ],
    "report integrity --config": lambda cfg, src, out: [
        "report", "integrity", out, "--source", src, "--config", cfg, "--json"
    ],
    "report vault --config": lambda cfg, src, out: [
        "report", "vault", out, "--config", cfg, "--json"
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

    argv = _COMMANDS[label](cfg, str(src), str(out))
    result = runner.invoke(app, argv, env=_WIDE_ENV, catch_exceptions=False)
    combined = (result.stdout or "") + (result.stderr or "")
    # The secret on the malformed line must never surface...
    assert _SENTINEL not in combined, (
        f"`decoy {' '.join(argv)}` leaked the config source line into its output:\n{combined}"
    )
    # ...and the sanitized message MUST have fired, proving the parse path was
    # actually reached (not a vacuous pass on a missing-arg error upstream).
    assert "could not parse YAML" in combined, (
        f"`decoy {' '.join(argv)}` did not reach the sanitized YAML-parse path; "
        f"the sentry would pass vacuously. Output:\n{combined}"
    )
