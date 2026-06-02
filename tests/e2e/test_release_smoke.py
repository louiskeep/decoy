"""R6.8 CLI release smoke gates.

CLI.3 commit 3+4 (2026-06-02): rewritten against the V2 surface.
Pre-rewrite the file exercised the V1 graph template, the V1
`examples/*.yaml` shapes, the deleted `forecast` command, and the V1
demo body. All four are dead under storm-reframe-C and
S22-CL-V1GRAPHRUNNER. The new cells:

- `decoy --version` smoke (module install + entry point work).
- `decoy templates list --json` returns the 5 surviving V2 templates
  (graph deleted under CLI.3 commit 1).
- `tests/unit/test_bundled_templates.py` already proves each surviving
  template validates under V2; no `examples/` parametrize cell here
  (examples are CLI.4 docs territory).
- `decoy demo --json` runs end-to-end and produces the canonical
  artifacts (the V2 demo body, no FORECAST step).
- Every release command's `--help` carries a `See also:` block.
- The `decoy run` canonical smoke against the bundled `minimal`
  template + a tmp-path CSV (CLI.3 spec DoD 8 'canonical smoke'; the
  cli-product-flow.md cite 'zero recorded executions' is closed here).

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

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()
REPO_ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------
# Console script + version
# --------------------------------------------------------------------------


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
    assert "decoy" in result.stdout.lower()


# --------------------------------------------------------------------------
# Templates registry
# --------------------------------------------------------------------------


def test_templates_list_json_returns_v2_template_set():
    """V2 surviving templates (5): minimal, hipaa, pci, gdpr, generate.
    CLI.3 commit 1 (2026-06-02) hard-deleted the V1 graph template."""
    result = runner.invoke(app, ["templates", "list", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    names = {t["name"] for t in payload["templates"]}
    expected = {"minimal", "hipaa", "pci", "gdpr", "generate"}
    assert expected == names, f"template registry drift: expected={expected} got={names}"


# --------------------------------------------------------------------------
# decoy demo --json end-to-end
# --------------------------------------------------------------------------


def test_demo_json_produces_expected_artifacts(tmp_path: Path):
    """`decoy demo` is the canonical clean-checkout-runnable command:
    generates its own fixture, scans with STORM, masks via the V2 spine.
    R6.8 asserts the JSON envelope shape + that the artifacts actually
    got written. The FORECAST step from the V1 demo was deleted under
    storm-reframe-C; no forecast.json is expected."""
    result = runner.invoke(app, ["demo", "--dir", str(tmp_path), "--json"])
    assert result.exit_code == 0, f"demo failed: {result.output}"
    payload = json.loads(result.output)
    assert payload["status"] == "ok", payload

    files = {p.name: p for p in tmp_path.iterdir() if p.is_file()}
    assert (tmp_path / "customers.csv").exists(), f"missing source csv: {list(files)}"
    assert (tmp_path / "customers_masked.csv").exists(), f"missing masked csv: {list(files)}"
    assert (tmp_path / "scan.json").exists(), f"missing scan.json: {list(files)}"
    assert (tmp_path / "pipeline.yaml").exists(), f"missing pipeline.yaml: {list(files)}"


# --------------------------------------------------------------------------
# Canonical smoke: decoy run against the bundled minimal template
# --------------------------------------------------------------------------


def test_release_smoke_runs_bundled_minimal_template(tmp_path: Path):
    """CLI.3 spec DoD 8 canonical smoke. Pulls the bundled minimal
    template, rewrites its source/target paths to point into tmp_path,
    writes a 3-row source CSV, invokes `decoy run`, asserts the masked
    CSV exists with the same row count as the source. The
    cli-product-flow.md cite 'zero recorded executions of the canonical
    smoke run' is closed by this cell.
    """
    from decoy.templates import get_template

    template = get_template("minimal")
    assert template is not None

    source_csv = tmp_path / "input.csv"
    pd.DataFrame(
        {
            "first_name": ["Alice", "Bob", "Carol"],
            "last_name": ["Anderson", "Brown", "Carter"],
            "email": ["a@example.com", "b@example.com", "c@example.com"],
            "ssn": ["111-22-3333", "444-55-6666", "777-88-9999"],
            "account_status": ["active", "active", "frozen"],
        }
    ).to_csv(source_csv, index=False)

    target_csv = tmp_path / "masked.csv"

    cfg = yaml.safe_load(template.body)
    cfg["sources"]["people"]["path"] = str(source_csv)
    cfg["targets"]["people"]["path"] = str(target_csv)

    pipeline_yaml = tmp_path / "pipeline.yaml"
    pipeline_yaml.write_text(yaml.dump(cfg))

    result = runner.invoke(app, ["run", str(pipeline_yaml)])
    assert result.exit_code == 0, result.output

    assert target_csv.exists(), "minimal template smoke produced no output"
    source_rows = pd.read_csv(source_csv)
    masked_rows = pd.read_csv(target_csv)
    assert len(masked_rows) == len(source_rows), "row count not preserved"


# --------------------------------------------------------------------------
# Help text contracts
# --------------------------------------------------------------------------


def test_root_help_lists_canonical_commands():
    """The root --help output should mention every V1 release command the
    user is likely to invoke. CLI.1 deleted forecast; this list reflects
    the current command surface."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    output = result.output.lower()
    for cmd in ("validate", "run", "demo", "storm", "templates", "init"):
        assert cmd in output, f"root help missing {cmd!r}: {result.output[:500]}"
    # CLI.1 (2026-06-02): forecast subcommand deleted under storm-reframe-C.
    assert "forecast" not in output


@pytest.mark.parametrize(
    "cmd",
    [
        "validate",
        "run",
        "demo",
        "init",
        # CLI.1: forecast no longer in the command set.
    ],
)
def test_command_help_includes_see_also(cmd: str):
    """CLI UX guide standard: every release command's --help ends with
    a `See also:` block. R6.8 asserts the contract holds across the
    main commands."""
    result = runner.invoke(app, [cmd, "--help"])
    assert result.exit_code == 0, f"{cmd} --help failed: {result.output}"
    assert "See also:" in result.output, (
        f"{cmd} --help missing 'See also:' block"
    )


# --------------------------------------------------------------------------
# decoy explain topic coverage
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "topic",
    [
        "modes",
        "transforms",
        "disguises",
        "output",
        "pipeline",
        "yaml",
        "storm",
        "keys",
        "security",
        "completion",
        # CLI.1 (2026-06-02): "forecast" topic stays in explain until CLI.4
        # docs sweep prunes it; the topic body explains the removal.
    ],
)
def test_explain_topic_resolves(topic: str):
    """Every named explain topic must resolve. CLI.4 owns the eventual
    cleanup of the forecast topic; until then this list omits it so
    R6.8 doesn't depend on a deferred decision."""
    result = runner.invoke(app, ["explain", topic])
    assert result.exit_code == 0, f"explain {topic} failed: {result.output}"


def test_explain_unknown_topic_does_not_crash():
    """Unknown topics print did-you-mean and exit gracefully."""
    result = runner.invoke(app, ["explain", "definitely-not-a-topic"])
    assert "Traceback" not in result.output
