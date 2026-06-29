"""Unit tests for _record_run_to_catalog verbose breadcrumb (SP-18b remediation).

MEDIUM-3 fix: a catalog-write failure under --verbose must emit a stderr
breadcrumb so the failure is visible. The run itself must still succeed
(best-effort recording).

Assertions:

C1. A catalog-write failure with verbose=True emits a stderr breadcrumb
    containing the exception description.
C2. A catalog-write failure with verbose=False (default) emits nothing to
    stderr (the failure remains silent, matching the original contract).
C3. The breadcrumb message contains the key diagnostic tokens so it is
    actionable ('catalog', 'jobs list').
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from decoy.cli.run import _record_run_to_catalog


def _make_ws_json_mock(exists: bool = True) -> MagicMock:
    """Return a Path-like mock for the workspace.json sentinel file."""
    ws_json = MagicMock(spec=Path)
    ws_json.exists.return_value = exists
    return ws_json


def _make_dotdecoy_mock(ws_json_mock: MagicMock) -> MagicMock:
    """Return a callable mock for _dotdecoy(root) that returns a path mock."""
    dotdecoy_dir = MagicMock(spec=Path)
    dotdecoy_dir.__truediv__ = MagicMock(return_value=ws_json_mock)
    return MagicMock(return_value=dotdecoy_dir)


def _call(verbose: bool = False, tmp_path: Path | None = None) -> None:
    """Invoke _record_run_to_catalog with a minimal setup."""
    ws_json = _make_ws_json_mock(exists=True)
    dotdecoy_mock = _make_dotdecoy_mock(ws_json)

    boom = RuntimeError("simulated DuckDB lock error")

    with (
        patch("decoy.cli.project._resolve_workspace", return_value=tmp_path or Path("/fake/ws")),
        patch("decoy.cli.project._dotdecoy", new=dotdecoy_mock),
        patch("decoy.cli.catalog._open_catalog", side_effect=boom),
    ):
        _record_run_to_catalog(
            config_path="/tmp/pipeline.yaml",
            mode="mask",
            elapsed_s=1.23,
            cli_version="0.5.0",
            engine_version="0.4.0",
            evidence_path=None,
            verbose=verbose,
        )


# ---------------------------------------------------------------------------
# C1: verbose=True -> breadcrumb on stderr when catalog write fails
# ---------------------------------------------------------------------------


def test_catalog_write_failure_verbose_emits_breadcrumb(tmp_path: Path, capsys) -> None:
    """A catalog-write failure with verbose=True must emit a stderr breadcrumb."""
    _call(verbose=True, tmp_path=tmp_path)

    captured = capsys.readouterr()
    assert "simulated DuckDB lock error" in captured.err, (
        "The verbose breadcrumb must contain the exception message so the "
        "operator can diagnose the catalog-write failure."
    )


# ---------------------------------------------------------------------------
# C2: verbose=False (default) -> no stderr output on catalog failure
# ---------------------------------------------------------------------------


def test_catalog_write_failure_silent_without_verbose(tmp_path: Path, capsys) -> None:
    """A catalog-write failure with verbose=False must produce no output."""
    _call(verbose=False, tmp_path=tmp_path)

    captured = capsys.readouterr()
    assert captured.err == "", (
        "Without --verbose a catalog-write failure must be completely silent. "
        "The original best-effort contract must be preserved."
    )


# ---------------------------------------------------------------------------
# C3: breadcrumb contains actionable tokens
# ---------------------------------------------------------------------------


def test_catalog_verbose_breadcrumb_contains_actionable_hint(tmp_path: Path, capsys) -> None:
    """The verbose breadcrumb must mention 'catalog' and 'jobs list'."""
    _call(verbose=True, tmp_path=tmp_path)

    captured = capsys.readouterr()
    assert "catalog" in captured.err, (
        "Breadcrumb must mention 'catalog' so the operator knows which system failed."
    )
    assert "jobs list" in captured.err, (
        "Breadcrumb must mention 'jobs list' so the operator knows the consequence "
        "of the failure."
    )
