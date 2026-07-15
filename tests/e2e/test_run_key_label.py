"""End-to-end tests for `decoy run`'s key_label resolution.

Doc/config mismatch fix: `decoy explain keys` / `decoy explain pipeline` used
to document a top-level `key_label:` YAML field as a working alternative to
`--key-label`. It never was -- `decoy_engine.config.PipelineConfig` declares
no `key_label` field and sets `model_config = ConfigDict(extra="forbid")`, so
any config with a top-level `key_label:` fails Pydantic validation before the
value is ever used. `_detect_key_label` (the CLI-side raw-YAML reader that
used to feed this field into the resolver) has been removed: it read the
raw top-level key before `PipelineConfig.model_validate` ran, so it could
observe the value, but a run that reached it always died moments later at
validation regardless -- the read could never produce a working run.

`--key-label` is, and always was, the only live mechanism. These tests lock
in the real (rejected) behavior of the YAML field and the real (working)
behavior of the flag, so the docs and the code cannot drift apart again.
"""

from __future__ import annotations

import secrets
from pathlib import Path

import yaml
from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()


def _generate_pipeline(tmp_path: Path, *, top_level_key_label: str | None = None) -> Path:
    """Minimal pure-generate V2 pipeline; optionally carries a top-level
    `key_label:` field (the shape the docs used to -- wrongly -- describe)."""
    cfg: dict = {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {},
        "tables": [
            {
                "name": "employees",
                "row_count": 5,
                "generate_columns": [
                    {"name": "first_name", "type": "faker", "faker_type": "first_name"},
                ],
            }
        ],
        "targets": {
            "employees": {
                "type": "file",
                "format": "csv",
                "path": str(tmp_path / "employees.csv"),
            }
        },
    }
    if top_level_key_label is not None:
        cfg["key_label"] = top_level_key_label
    p = tmp_path / "pipeline.yaml"
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return p


class TestTopLevelYamlKeyLabelIsRejected:
    """A top-level `key_label:` in the pipeline YAML is NOT a supported
    field -- PipelineConfig's `extra="forbid"` rejects it. Locks in the real
    behavior so `decoy explain` never again documents this as working."""

    def test_top_level_key_label_fails_validation(self, tmp_path: Path) -> None:
        cfg = _generate_pipeline(tmp_path, top_level_key_label="customers_q4")
        result = runner.invoke(app, ["run", str(cfg)])

        assert result.exit_code != 0, (
            "a top-level YAML key_label: must not silently succeed"
        )
        assert "key_label" in result.output
        assert not (tmp_path / "employees.csv").exists(), (
            "a rejected config must not produce output"
        )

    def test_top_level_key_label_fails_even_with_master_key(self, tmp_path: Path) -> None:
        """Even when --master-key + top-level YAML key_label are both
        present (the exact shape the old docs recommended), the run still
        fails: PipelineConfig.model_validate rejects the raw config
        regardless of what the CLI did with the value beforehand."""
        cfg = _generate_pipeline(tmp_path, top_level_key_label="customers_q4")
        master_key = secrets.token_hex(32)
        result = runner.invoke(app, ["run", str(cfg), "--master-key", master_key])

        assert result.exit_code != 0
        assert not (tmp_path / "employees.csv").exists()

    def test_top_level_key_label_error_does_not_claim_yaml_support(
        self, tmp_path: Path
    ) -> None:
        """Regression guard for the doc/config mismatch itself: no CLI-owned
        message may claim a top-level YAML key_label: works."""
        cfg = _generate_pipeline(tmp_path, top_level_key_label="customers_q4")
        master_key = secrets.token_hex(32)
        result = runner.invoke(app, ["run", str(cfg), "--master-key", master_key])

        assert "top-level" not in result.output
        assert "'key_label:'" not in result.output


class TestKeyLabelFlagWorks:
    """`--key-label` is the one real mechanism; it must keep working."""

    def test_master_key_with_key_label_flag_succeeds(self, tmp_path: Path) -> None:
        cfg = _generate_pipeline(tmp_path)
        master_key = secrets.token_hex(32)
        result = runner.invoke(
            app,
            ["run", str(cfg), "--master-key", master_key, "--key-label", "customers_q4"],
        )

        assert result.exit_code == 0, result.output
        assert (tmp_path / "employees.csv").exists()

    def test_master_key_without_key_label_is_usage_error(self, tmp_path: Path) -> None:
        cfg = _generate_pipeline(tmp_path)
        master_key = secrets.token_hex(32)
        result = runner.invoke(app, ["run", str(cfg), "--master-key", master_key])

        # _build_resolver raises typer.BadParameter, which Click/Typer
        # handles as its own UsageError -- exit code 2, distinct from the
        # app's EXIT_USAGE=1 (that constant covers errors the run() body
        # raises itself and routes through the try/except at the bottom of
        # run(); a parameter-callback-time BadParameter never reaches it).
        assert result.exit_code == 2, (
            f"expected Click UsageError exit code 2, got {result.exit_code}. "
            f"output={result.output!r}"
        )
        assert "--key-label" in result.output
        # The old message pointed operators at a YAML field that cannot
        # work; the fixed message must not repeat that claim.
        assert "top-level" not in result.output
