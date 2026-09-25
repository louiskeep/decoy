"""End-to-end test for `decoy run` against a cloud source without the
`[cloud]` extra installed (CLI install DX, 2026-09-25, acceptance test 4).

boto3/google-cloud-storage moved from decoy-engine hard dependencies to an
opt-in `[cloud]` extra. A pipeline whose sources/targets point at S3 or GCS
must fail closed with the exact install line, not a raw traceback -- proven
here end-to-end through `decoy run`, not just at the extras.py unit level
(see tests/unit/test_extras.py for the pure-logic coverage this feeds).

Blocks the `boto3` import via a meta-path finder (same technique as
tests/e2e/test_run_mask_secret.py's `_BlockKeyprovider`) so the test is
deterministic regardless of whether boto3 happens to already be installed
in the dev/CI environment running this suite.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from importlib.abc import MetaPathFinder
from pathlib import Path

import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_USAGE

runner = CliRunner()

_BOTO3_MOD = "boto3"


class _BlockBoto3(MetaPathFinder):
    """Meta-path finder that makes `import boto3` raise, to simulate an
    install without the `[cloud]` extra. Returns None for every other
    module so normal imports are untouched."""

    def find_spec(self, fullname, path, target=None):
        if fullname == _BOTO3_MOD:
            raise ModuleNotFoundError(f"No module named {_BOTO3_MOD!r}", name=fullname)
        return None


@contextmanager
def _simulate_no_cloud_extra():
    """Force a FRESH `import boto3` to raise, without touching any
    already-imported module (this dev venv may still have boto3 installed
    from before the extras split; this block is surgical regardless)."""
    finder = _BlockBoto3()
    saved = sys.modules.pop(_BOTO3_MOD, None)
    sys.meta_path.insert(0, finder)
    try:
        yield
    finally:
        try:
            sys.meta_path.remove(finder)
        except ValueError:
            pass
        if saved is not None:
            sys.modules[_BOTO3_MOD] = saved


def _s3_source_pipeline(tmp_path: Path) -> Path:
    cfg = {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {
            "accounts": {
                "type": "s3",
                "format": "csv",
                "bucket": "test-bucket",
                "key": "accounts.csv",
            }
        },
        "tables": [
            {
                "name": "accounts",
                "columns": [
                    {
                        "name": "ssn",
                        "strategy": "fpe",
                        "namespace": "ssn_identity",
                        "provider_config": {"charset": "digits"},
                    },
                ],
            }
        ],
        "targets": {
            "accounts": {
                "type": "file",
                "format": "csv",
                "path": str(tmp_path / "out.csv"),
            }
        },
    }
    p = tmp_path / "pipeline.yaml"
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return p


class TestCloudSourceWithoutExtra:
    def test_s3_source_without_cloud_extra_exits_usage_with_install_line(
        self, tmp_path: Path
    ) -> None:
        cfg = _s3_source_pipeline(tmp_path)
        with _simulate_no_cloud_extra():
            result = runner.invoke(app, ["run", str(cfg)])
        assert result.exit_code == EXIT_USAGE, (
            f"expected EXIT_USAGE ({EXIT_USAGE}), got {result.exit_code}. output={result.output!r}"
        )
        # Rich wraps stderr to the terminal width, so the install line can
        # land on its own line; collapse whitespace before matching rather
        # than asserting an exact unbroken substring.
        assert "pip install decoy-cli[cloud]" in " ".join(result.output.split()), result.output
        # Not a raw traceback: no bare Python frame markers leaking to the
        # operator's terminal.
        assert "Traceback (most recent call last)" not in result.output

    def test_s3_source_without_cloud_extra_json_mode_names_the_install_line(
        self, tmp_path: Path
    ) -> None:
        cfg = _s3_source_pipeline(tmp_path)
        with _simulate_no_cloud_extra():
            result = runner.invoke(app, ["run", str(cfg), "--json"])
        assert result.exit_code == EXIT_USAGE, result.output
        assert "pip install decoy-cli[cloud]" in " ".join(result.output.split()), result.output
