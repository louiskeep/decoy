"""`decoy vault info` e2e tests.

Creates a real vault via `decoy run --vault`, then exercises the
`decoy vault info` command: happy path, --json envelope, and the
wrong-seed error path.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_USAGE

pytest.importorskip("cryptography")

runner = CliRunner()


def _pipeline(tmp_path: Path, rows: int = 30) -> Path:
    """Write a small CSV + pipeline config with a vaulted hash column."""
    src = tmp_path / "in.csv"
    pd.DataFrame(
        {
            "email": [f"u{i}@example.com" for i in range(rows)],
            "name": [f"Person {i}" for i in range(rows)],
        }
    ).to_csv(src, index=False)
    cfg = {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {
            "accounts": {"type": "file", "format": "csv", "path": str(src)}
        },
        "tables": [
            {
                "name": "accounts",
                "columns": [
                    {
                        "name": "email",
                        "strategy": "hash",
                        "namespace": "email_ns",
                        "vault": True,
                    },
                    {"name": "name", "strategy": "redact"},
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


@pytest.fixture()
def vault_setup(tmp_path: Path):
    """Run a mask pipeline with --vault; yield (cfg_path, vault_path)."""
    cfg = _pipeline(tmp_path)
    vault = tmp_path / "vault.bin"
    result = runner.invoke(app, ["run", str(cfg), "--vault", str(vault)])
    assert result.exit_code == 0, result.output
    assert vault.exists() and vault.stat().st_size > 0
    return cfg, vault


class TestVaultInfoHappyPath:
    def test_exit_0_and_entry_count_positive(self, vault_setup) -> None:
        cfg, vault = vault_setup
        result = runner.invoke(
            app, ["vault", "info", str(vault), "--config", str(cfg)]
        )
        assert result.exit_code == 0, result.output
        assert "entries" in result.output or "OK" in result.output

    def test_namespaces_reported(self, vault_setup) -> None:
        cfg, vault = vault_setup
        result = runner.invoke(
            app, ["vault", "info", str(vault), "--config", str(cfg)]
        )
        assert result.exit_code == 0, result.output
        # The namespace we declared is "email_ns"
        assert "email_ns" in result.output

    def test_json_envelope_keys(self, vault_setup) -> None:
        cfg, vault = vault_setup
        result = runner.invoke(
            app, ["vault", "info", str(vault), "--config", str(cfg), "--json"]
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output.strip())
        assert payload["command"] == "vault-info"
        assert payload["status"] == "ok"
        assert payload["vault"] == str(vault)
        assert isinstance(payload["entries"], int) and payload["entries"] > 0
        assert isinstance(payload["namespaces"], list) and len(payload["namespaces"]) > 0
        assert "ambiguous_dropped" in payload

    def test_quiet_exits_0(self, vault_setup) -> None:
        cfg, vault = vault_setup
        result = runner.invoke(
            app, ["vault", "info", str(vault), "--config", str(cfg), "--quiet"]
        )
        assert result.exit_code == 0
        # quiet mode produces no stdout
        assert result.output.strip() == ""


class TestVaultInfoErrors:
    def test_wrong_seed_exits_usage(self, vault_setup, tmp_path: Path) -> None:
        cfg, vault = vault_setup
        # Build a config with a different seed; vault must refuse to decrypt.
        wrong_cfg = yaml.safe_load(cfg.read_text(encoding="utf-8"))
        wrong_cfg["global_settings"]["seed"] = 99
        wrong_path = tmp_path / "wrong.yaml"
        wrong_path.write_text(yaml.safe_dump(wrong_cfg), encoding="utf-8")

        result = runner.invoke(
            app, ["vault", "info", str(vault), "--config", str(wrong_path)]
        )
        assert result.exit_code == EXIT_USAGE
        # Must not print a Python traceback.
        assert "Traceback" not in result.output

    def test_wrong_seed_json_error_envelope(self, vault_setup, tmp_path: Path) -> None:
        cfg, vault = vault_setup
        wrong_cfg = yaml.safe_load(cfg.read_text(encoding="utf-8"))
        wrong_cfg["global_settings"]["seed"] = 99
        wrong_path = tmp_path / "wrong2.yaml"
        wrong_path.write_text(yaml.safe_dump(wrong_cfg), encoding="utf-8")

        result = runner.invoke(
            app,
            ["vault", "info", str(vault), "--config", str(wrong_path), "--json"],
        )
        assert result.exit_code == EXIT_USAGE
        payload = json.loads(result.output.strip())
        assert payload["command"] == "vault-info"
        assert payload["status"] == "error"
        assert "error" in payload
