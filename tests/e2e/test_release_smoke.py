"""R6.8 CLI release smoke gates.

The named-command gates the R6.1 release-readiness checklist invokes
against the CLI repo. Each test maps to one line in the CLI V1 audit
under "Clean install + console script + package contents + canonical
commands JSON envelopes."

Out of scope for R6.8 (deferred / handled elsewhere):

- Clean install of the published package (pip install decoy) -- requires
  a published release artifact. R5.6 fresh-VM smoke covers this on the
  integrator side; the CLI's CI runs against the source tree.
- Real Postgres / cloud connector tests -- file-only V1 scope.
- OIDC -- N/A; CLI has no auth surface.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()
REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "examples"


# ── Console script + version ────────────────────────────────────────────────


def test_decoy_module_invocation_succeeds():
    """`python -m decoy --version` is the smoke that catches a botched
    package install or a broken `__main__`."""
    result = subprocess.run(
        [sys.executable, "-m", "decoy", "--version"],
        capture_output=True,
        text=True,
        timeout=15,
        env={**__import__("os").environ, "PYTHONPATH": str(REPO_ROOT / "src")},
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, f"non-zero exit: stderr={result.stderr[:200]}"
    # Output looks like "decoy 0.1.0" or similar; just confirm a version
    # token is present.
    assert "decoy" in result.stdout.lower()


# ── `decoy templates list --json` shape ────────────────────────────────────


def test_templates_list_json_returns_expected_names():
    """The 6 V1 templates: minimal, hipaa, pci, gdpr, generate, graph."""
    result = runner.invoke(app, ["templates", "list", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    names = {t["name"] for t in payload["templates"]}
    expected = {"minimal", "hipaa", "pci", "gdpr", "generate", "graph"}
    assert expected.issubset(names), f"missing templates: {expected - names}"


# ── `decoy validate` against bundled examples ───────────────────────────────


@pytest.mark.parametrize("example", [
    "mask_example.yaml",
    "generate_example.yaml",
    "fixed_width_example.yaml",
    "graph_example.yaml",
])
def test_bundled_example_validates_cleanly(example: str):
    """Every bundled example MUST validate. Validation does not require
    the input file to exist; only the YAML shape is checked."""
    example_path = EXAMPLES / example
    assert example_path.exists(), f"missing example: {example}"
    result = runner.invoke(app, ["validate", str(example_path), "--json"])
    assert result.exit_code == 0, (
        f"{example} failed validation. exit={result.exit_code}\n{result.output}"
    )
    payload = json.loads(result.output)
    assert payload["status"] == "ok", (
        f"{example} validation did not report ok: {payload}"
    )


# ── `decoy demo --json` end-to-end (no external state required) ────────────


def test_demo_json_produces_expected_artifacts(tmp_path: Path):
    """`decoy demo` is the canonical clean-checkout-runnable command:
    generates its own fixture, scans it, FORECASTs, and masks. R6.8 asserts
    the JSON envelope shape + that the artifacts actually got written."""
    result = runner.invoke(app, ["demo", "--dir", str(tmp_path), "--json"])
    assert result.exit_code == 0, f"demo failed: {result.output}"
    payload = json.loads(result.output)
    assert payload["status"] == "ok", payload

    # The demo writes a scan JSON, a forecast JSON, a masked CSV, and an
    # input fixture. Spot-check the canonical artifacts.
    files = {p.name: p for p in tmp_path.iterdir() if p.is_file()}
    # Demo names vary by version; assert at least the canonical shapes.
    has_csv = any(p.suffix == ".csv" for p in files.values())
    has_json = any(p.suffix == ".json" for p in files.values())
    assert has_csv, f"demo produced no CSV: {list(files)}"
    assert has_json, f"demo produced no JSON: {list(files)}"


# ── Help text contracts ────────────────────────────────────────────────────


def test_root_help_lists_canonical_commands():
    """The root --help output should mention the V1 commands a user is
    likely to invoke first."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    output = result.output.lower()
    for cmd in ("validate", "run", "demo", "storm", "forecast", "templates", "init"):
        assert cmd in output, f"root help missing {cmd!r}: {result.output[:500]}"


@pytest.mark.parametrize("cmd", [
    "validate", "run", "demo", "forecast", "init",
])
def test_command_help_includes_see_also(cmd: str):
    """CLI UX guide standard: every release command's --help ends with
    a `See also:` block. R6.8 asserts the contract holds across the
    main commands; drift signals a help-template regression."""
    result = runner.invoke(app, [cmd, "--help"])
    assert result.exit_code == 0, f"{cmd} --help failed: {result.output}"
    assert "See also:" in result.output, (
        f"{cmd} --help missing 'See also:' block"
    )


# ── `decoy explain` topic coverage ─────────────────────────────────────────


@pytest.mark.parametrize("topic", [
    "modes", "transforms", "disguises", "output", "pipeline",
    "yaml", "storm", "forecast", "keys", "security", "completion",
])
def test_explain_topic_resolves(topic: str):
    """Every named explain topic must resolve (R4.7 added yaml + security)."""
    result = runner.invoke(app, ["explain", topic])
    assert result.exit_code == 0, f"explain {topic} failed: {result.output}"


def test_explain_unknown_topic_does_not_crash():
    """Unknown topics print did-you-mean and exit gracefully."""
    result = runner.invoke(app, ["explain", "definitely-not-a-topic"])
    # Either exit 0 with a "did you mean" or non-zero with a clear error.
    # Don't be strict on the exit code; do be strict on no traceback.
    assert "Traceback" not in result.output
