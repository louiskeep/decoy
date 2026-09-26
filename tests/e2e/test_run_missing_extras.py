"""End-to-end tests for `decoy run` against a cloud source/target
(CLI install DX).

boto3/google-cloud-storage moved from decoy-engine hard dependencies to an
opt-in `[cloud]` extra. The original acceptance criterion assumed installing
`[cloud]` would make an s3/gcs job actually run; that's false -- `decoy run`'s own I/O helpers (`_load_sources_from_config` /
`_write_mask_outputs` / `_run_chunked_mask`) only ever handle a `path`-typed
local source/target, so a cloud endpoint was silently skipped and the run
reported `{"status": "ok"}`, exit 0, with the masked output dropped. There
is no dependency on whether the SDK is installed: `decoy run` cannot execute
against S3/GCS at all today.

`check_cloud_endpoints_supported` now refuses that job up front with a typed
error, unconditionally -- proven here end-to-end through `decoy run`, not
just at the extras.py unit level (see tests/unit/test_extras.py for the
pure-logic coverage this feeds, including the still-valid, separately
testable `check_cloud_endpoints` SDK-presence check that this scenario never
reaches in practice now that the unsupported-endpoint check runs first).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_USAGE

runner = CliRunner()


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


def _gcs_target_pipeline(tmp_path: Path) -> Path:
    src = tmp_path / "accounts.csv"
    src.write_text("ssn\n123456789\n", encoding="utf-8")
    cfg = {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {
            "accounts": {"type": "file", "format": "csv", "path": str(src)},
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
                "type": "gcs",
                "format": "csv",
                "bucket": "test-bucket",
                "object": "out.csv",
            },
        },
    }
    p = tmp_path / "pipeline.yaml"
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return p


class TestCloudEndpointUnsupportedByRun:
    """`decoy run` fails closed on any s3/gcs source or target -- never a
    silent skip that reports success with the masked output dropped.
    This holds regardless of whether `[cloud]` is installed:
    the gap is that `decoy run` has no cloud I/O path at all, not that the
    SDK is missing.

    Every test here also proves the refusal happens BEFORE the engine runs:
    a typed error raised after `run_pipeline` / `run_mask_pipeline_chunked`
    had already masked the data would still exit EXIT_USAGE, so the exit
    code alone cannot tell the two apart."""

    @pytest.fixture(autouse=True)
    def engine_calls(self, monkeypatch: pytest.MonkeyPatch):
        calls: list[str] = []

        def _spy(name: str):
            def _called(*_args, **_kwargs):
                calls.append(name)
                raise AssertionError(f"{name} ran before the cloud refusal")

            return _called

        monkeypatch.setattr("decoy_engine.run_pipeline", _spy("run_pipeline"))
        monkeypatch.setattr(
            "decoy_engine.run_mask_pipeline_chunked", _spy("run_mask_pipeline_chunked")
        )
        yield calls
        assert calls == [], f"engine entry points were invoked: {calls}"

    def test_s3_source_fails_closed_not_silently_skipped(self, tmp_path: Path) -> None:
        cfg = _s3_source_pipeline(tmp_path)
        result = runner.invoke(app, ["run", str(cfg)])
        assert result.exit_code == EXIT_USAGE, (
            f"expected EXIT_USAGE ({EXIT_USAGE}), got {result.exit_code}. "
            f"A cloud source must never exit 0 with the output silently dropped. "
            f"output={result.output!r}"
        )
        collapsed = " ".join(result.output.split())
        assert "cannot run through" in collapsed, result.output
        assert "s3" in collapsed and "accounts" in collapsed, result.output
        assert "Traceback (most recent call last)" not in result.output

    def test_gcs_target_fails_closed_not_silently_skipped(self, tmp_path: Path) -> None:
        cfg = _gcs_target_pipeline(tmp_path)
        result = runner.invoke(app, ["run", str(cfg)])
        assert result.exit_code == EXIT_USAGE, (
            f"expected EXIT_USAGE ({EXIT_USAGE}), got {result.exit_code}. output={result.output!r}"
        )
        collapsed = " ".join(result.output.split())
        assert "cannot run through" in collapsed, result.output
        assert "gcs" in collapsed and "accounts" in collapsed, result.output

    def test_json_mode_reports_the_same_typed_failure(self, tmp_path: Path) -> None:
        cfg = _s3_source_pipeline(tmp_path)
        result = runner.invoke(app, ["run", str(cfg), "--json"])
        assert result.exit_code == EXIT_USAGE, result.output
        assert '"status": "error"' in result.output, result.output
        assert "cannot run through" in result.output, result.output
        # Never the false-success shape this check exists to prevent.
        assert '"status": "ok"' not in result.output, result.output

    def test_chunked_run_fails_closed_too(self, tmp_path: Path) -> None:
        # The refusal lives in the shared I/O helpers, so the --chunked path
        # needs its own proof: it goes through _run_chunked_mask, not
        # _load_sources_from_config.
        cfg = _gcs_target_pipeline(tmp_path)
        result = runner.invoke(app, ["run", str(cfg), "--chunked"])
        assert result.exit_code == EXIT_USAGE, result.output
        collapsed = " ".join(result.output.split())
        assert "cannot run through" in collapsed, result.output
        assert "gcs" in collapsed and "accounts" in collapsed, result.output
