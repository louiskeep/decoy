"""SP-16: validate --fail-on-warning + multi-message --json output.

Tests run BEFORE the implementation so they fail first (TDD requirement).

Assertions:
A1. --fail-on-warning exits non-zero when a warning exists (output target already exists).
A2. --fail-on-warning exits 0 when no warnings (clean config, no pre-existing output).
A3. --json emits a `messages` list with severity/code/message/location fields.
A4. --json on an invalid config emits multiple errors in `messages` (multi-message, not first-fail).
A5. Human-readable output (default) is unaffected by the messages contract.
A6. The `messages` list is present on success with an empty or non-empty list.
"""

from __future__ import annotations

import json as _json
from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_v2_mask_config(tmp_path: Path, out_name: str = "out.csv") -> tuple[dict, Path]:
    """Return a (config_dict, config_yaml_path) pair for a minimal valid V2 config.

    The target path is tmp_path/<out_name> so callers can pre-create it to
    trigger the overwrite warning.
    """
    src = tmp_path / "in.csv"
    pd.DataFrame({"customer_id": ["1", "2"], "name": ["a", "b"]}).to_csv(src, index=False)
    cfg = {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {
            "customers": {"type": "file", "format": "csv", "path": str(src)},
        },
        "tables": [
            {
                "name": "customers",
                "columns": [
                    {
                        "name": "customer_id",
                        "strategy": "faker",
                        "provider": "person_email",
                        "deterministic": True,
                        "namespace": "customer_identity",
                    },
                ],
            },
        ],
        "targets": {
            "customers": {"type": "file", "format": "csv", "path": str(tmp_path / out_name)},
        },
    }
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(cfg), encoding="utf-8")
    return cfg, p


# ---------------------------------------------------------------------------
# A1. --fail-on-warning exits non-zero when a warning exists
# ---------------------------------------------------------------------------


def test_validate_fail_on_warning_exits_nonzero_when_target_exists(tmp_path: Path):
    """A1: --fail-on-warning exits non-zero when any warning is present.

    Scenario: the output target file already exists on disk.
    validate is clean (no errors), but emits an overwrite advisory warning.
    With --fail-on-warning, CI must exit non-zero.
    """
    _cfg, p = _valid_v2_mask_config(tmp_path)
    # Pre-create the target so the overwrite-advisory warning fires.
    (tmp_path / "out.csv").write_text("id\n1\n", encoding="utf-8")

    result = runner.invoke(app, ["validate", str(p), "--fail-on-warning"])
    assert result.exit_code != 0, (
        "--fail-on-warning should exit non-zero when an output target already exists "
        f"(got exit {result.exit_code}). output: {result.output}"
    )


# ---------------------------------------------------------------------------
# A2. --fail-on-warning exits 0 when no warnings
# ---------------------------------------------------------------------------


def test_validate_fail_on_warning_exits_zero_when_no_warnings(tmp_path: Path):
    """A2: --fail-on-warning exits 0 when the config is clean (no warnings, no errors).

    The output target does NOT exist, so no overwrite warning fires.
    """
    _cfg, p = _valid_v2_mask_config(tmp_path)
    # Do NOT pre-create out.csv -- no warnings should fire.

    result = runner.invoke(app, ["validate", str(p), "--fail-on-warning"])
    assert result.exit_code == 0, (
        "--fail-on-warning should exit 0 on a clean config with no warnings "
        f"(got exit {result.exit_code}). output: {result.output}"
    )


# ---------------------------------------------------------------------------
# A3. --json emits `messages` list with structured fields
# ---------------------------------------------------------------------------


def test_validate_json_emits_messages_list_on_success(tmp_path: Path):
    """A3: --json on a clean config emits a `messages` list in the envelope."""
    _cfg, p = _valid_v2_mask_config(tmp_path)

    result = runner.invoke(app, ["validate", str(p), "--json"])
    assert result.exit_code == 0, result.output
    payload = _json.loads(result.stdout)
    assert "messages" in payload, f"Expected 'messages' key in JSON envelope. Got: {list(payload.keys())}"
    assert isinstance(payload["messages"], list)


def test_validate_json_messages_include_warnings_when_target_exists(tmp_path: Path):
    """A3 extension: when target exists, --json includes a warning-severity message."""
    _cfg, p = _valid_v2_mask_config(tmp_path)
    (tmp_path / "out.csv").write_text("id\n1\n", encoding="utf-8")

    result = runner.invoke(app, ["validate", str(p), "--json"])
    # Config is valid -> exit 0, but messages may include warnings
    payload = _json.loads(result.stdout)
    assert "messages" in payload
    warnings = [m for m in payload["messages"] if m.get("severity") == "warning"]
    assert warnings, f"Expected at least one warning in messages. Got: {payload['messages']}"
    w = warnings[0]
    assert "severity" in w
    assert "code" in w
    assert "message" in w
    # location is optional but should be present for file-target warnings
    assert "location" in w or "path" in w


def test_validate_json_messages_each_have_required_fields(tmp_path: Path):
    """A3 contract: each message in `messages` has severity, code, and message fields."""
    _cfg, p = _valid_v2_mask_config(tmp_path)
    (tmp_path / "out.csv").write_text("id\n", encoding="utf-8")

    result = runner.invoke(app, ["validate", str(p), "--json"])
    payload = _json.loads(result.stdout)
    for msg in payload.get("messages", []):
        assert "severity" in msg, f"Message missing 'severity': {msg}"
        assert "code" in msg, f"Message missing 'code': {msg}"
        assert "message" in msg, f"Message missing 'message': {msg}"
        assert msg["severity"] in ("error", "warning", "info"), (
            f"Unexpected severity value: {msg['severity']}"
        )


# ---------------------------------------------------------------------------
# A4. --json on invalid config emits multiple errors in `messages`
# ---------------------------------------------------------------------------


def test_validate_json_emits_multiple_errors_for_invalid_config(tmp_path: Path):
    """A4: pydantic ValidationError with multiple issues -> all appear in `messages`.

    A config missing both `version` and `tables` should produce at least 2 error
    messages in the JSON envelope (multi-message, not first-fail).
    """
    # Config missing both `version` and `tables` triggers multiple pydantic errors.
    bad_cfg = {
        "global_settings": {"seed": 42},
        "sources": {"t": {"type": "file", "format": "csv", "path": "./t.csv"}},
        "targets": {"t": {"type": "file", "format": "csv", "path": "./out.csv"}},
        # missing `version` and `tables`
    }
    p = tmp_path / "bad.yaml"
    p.write_text(yaml.dump(bad_cfg), encoding="utf-8")

    result = runner.invoke(app, ["validate", str(p), "--json"])
    assert result.exit_code != 0
    payload = _json.loads(result.stdout)
    assert "messages" in payload
    error_msgs = [m for m in payload["messages"] if m.get("severity") == "error"]
    assert len(error_msgs) >= 2, (
        f"Expected at least 2 error messages for a config missing version + tables. "
        f"Got: {error_msgs}"
    )


# ---------------------------------------------------------------------------
# A5. Human-readable output unaffected
# ---------------------------------------------------------------------------


def test_validate_human_readable_still_works_with_new_flags(tmp_path: Path):
    """A5: default (non-JSON) output still shows OK on a clean config."""
    _cfg, p = _valid_v2_mask_config(tmp_path)
    result = runner.invoke(app, ["validate", str(p)])
    assert result.exit_code == 0
    assert "OK" in result.stdout


def test_validate_human_readable_shows_warning_hint_when_target_exists(tmp_path: Path):
    """A5 extension: human-readable output mentions the overwrite warning when it fires."""
    _cfg, p = _valid_v2_mask_config(tmp_path)
    (tmp_path / "out.csv").write_text("id\n", encoding="utf-8")

    result = runner.invoke(app, ["validate", str(p)])
    # Should still exit 0 (warnings are not errors)
    assert result.exit_code == 0
    # Warning text should appear somewhere in combined output
    assert "warning" in result.output.lower() or "exist" in result.output.lower(), (
        f"Expected warning hint in human-readable output. Got: {result.output}"
    )


# ---------------------------------------------------------------------------
# A6. `messages` is always present in JSON output
# ---------------------------------------------------------------------------


def test_validate_json_messages_key_present_on_success_no_warnings(tmp_path: Path):
    """A6: `messages` is present even when there are no warnings -- empty list."""
    _cfg, p = _valid_v2_mask_config(tmp_path)
    # Ensure no pre-existing output file
    result = runner.invoke(app, ["validate", str(p), "--json"])
    payload = _json.loads(result.stdout)
    assert "messages" in payload
    assert payload["messages"] == []


@pytest.mark.parametrize("extra_flag", ["--fail-on-warning"])
def test_validate_flag_is_recognized(tmp_path: Path, extra_flag: str):
    """Flag smoke: --fail-on-warning is accepted by the CLI (no 'unrecognized option' error)."""
    _cfg, p = _valid_v2_mask_config(tmp_path)
    result = runner.invoke(app, ["validate", str(p), extra_flag])
    assert "No such option" not in result.output
    assert "Error: No such option" not in result.output
