"""End-to-end tests for `decoy unmask` (capability-gaps WS1, 2026-06-12).

The detokenization verb: `decoy run` masks, `decoy unmask` recovers the
fpe columns from the masked file using the SAME config (which carries
the seed -- the secret -- plus namespace/charset per column). Hash and
other one-way columns stay as-is and are reported irreversible.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_USAGE

runner = CliRunner()


def _pipeline(tmp_path: Path, *, seed: int = 42) -> Path:
    src = tmp_path / "accounts.csv"
    pd.DataFrame(
        {
            "ssn": ["123-45-6789", "987-65-4321", "111-22-3333"],
            "email": ["a@x.com", "b@x.com", "c@x.com"],
        }
    ).to_csv(src, index=False)
    cfg = {
        "version": 1,
        "global_settings": {"seed": seed},
        "sources": {"accounts": {"type": "file", "format": "csv", "path": str(src)}},
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
                    {
                        "name": "email",
                        "strategy": "hash",
                        "namespace": "email_identity",
                    },
                ],
            }
        ],
        "targets": {
            "accounts": {
                "type": "file",
                "format": "csv",
                "path": str(tmp_path / "masked.csv"),
            }
        },
    }
    cfg_path = tmp_path / "pipeline.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return cfg_path


def _run_mask(tmp_path: Path) -> Path:
    cfg_path = _pipeline(tmp_path)
    result = runner.invoke(app, ["run", str(cfg_path)])
    assert result.exit_code == 0, result.output
    masked = tmp_path / "masked.csv"
    assert masked.exists()
    return cfg_path


class TestUnmaskRoundTrip:
    def test_recovers_fpe_column_exactly(self, tmp_path: Path) -> None:
        cfg_path = _run_mask(tmp_path)
        masked = pd.read_csv(tmp_path / "masked.csv", dtype=str)
        assert masked["ssn"].tolist() != ["123-45-6789", "987-65-4321", "111-22-3333"]

        out = tmp_path / "recovered.csv"
        result = runner.invoke(
            app,
            ["unmask", str(cfg_path), str(tmp_path / "masked.csv"), "--output", str(out)],
        )
        assert result.exit_code == 0, result.output
        recovered = pd.read_csv(out, dtype=str)
        assert recovered["ssn"].tolist() == ["123-45-6789", "987-65-4321", "111-22-3333"]
        # Hash column is one-way: unchanged from the masked file.
        assert recovered["email"].tolist() == masked["email"].tolist()

    def test_json_report(self, tmp_path: Path) -> None:
        cfg_path = _run_mask(tmp_path)
        out = tmp_path / "recovered.csv"
        result = runner.invoke(
            app,
            [
                "unmask",
                str(cfg_path),
                str(tmp_path / "masked.csv"),
                "--output",
                str(out),
                "--json",
            ],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["command"] == "unmask"
        assert payload["status"] == "ok"
        by_col = {c["column"]: c for c in payload["columns"]}
        # DE-02: this round-trip configures no mask_secret_ref, so the FPE
        # reversal runs under the job_seed fallback and the engine reports it
        # as `reversed_unverified` (recovered, but not cryptographically
        # authenticated) rather than `reversed`.
        assert by_col["ssn"]["status"] == "reversed_unverified"
        assert by_col["email"]["status"] == "irreversible"

    def test_default_output_path(self, tmp_path: Path) -> None:
        cfg_path = _run_mask(tmp_path)
        result = runner.invoke(app, ["unmask", str(cfg_path), str(tmp_path / "masked.csv")])
        assert result.exit_code == 0, result.output
        assert (tmp_path / "masked.unmasked.csv").exists()


class TestUnmaskErrors:
    def test_missing_config_exits_usage(self, tmp_path: Path) -> None:
        masked = tmp_path / "masked.csv"
        masked.write_text("a\n1\n", encoding="utf-8")
        result = runner.invoke(app, ["unmask", str(tmp_path / "nope.yaml"), str(masked)])
        assert result.exit_code != 0

    def test_invalid_yaml_exits_usage(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text("not: [valid", encoding="utf-8")
        masked = tmp_path / "masked.csv"
        masked.write_text("a\n1\n", encoding="utf-8")
        result = runner.invoke(app, ["unmask", str(bad), str(masked)])
        assert result.exit_code == EXIT_USAGE

    def test_ambiguous_table_requires_flag(self, tmp_path: Path) -> None:
        cfg_path = _run_mask(tmp_path)
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        cfg["tables"].append(
            {
                "name": "orders",
                "columns": [
                    {
                        "name": "order_id",
                        "strategy": "fpe",
                        "namespace": "order_identity",
                        "provider_config": {"charset": "digits"},
                    }
                ],
            }
        )
        cfg["sources"]["orders"] = {
            "type": "file",
            "format": "csv",
            "path": str(tmp_path / "orders.csv"),
        }
        cfg["targets"]["orders"] = {
            "type": "file",
            "format": "csv",
            "path": str(tmp_path / "orders_out.csv"),
        }
        two_tables = tmp_path / "two.yaml"
        two_tables.write_text(yaml.safe_dump(cfg), encoding="utf-8")
        result = runner.invoke(app, ["unmask", str(two_tables), str(tmp_path / "masked.csv")])
        assert result.exit_code == EXIT_USAGE
        assert "--table" in result.output

    def test_explicit_table_flag_resolves_ambiguity(self, tmp_path: Path) -> None:
        cfg_path = _run_mask(tmp_path)
        out = tmp_path / "recovered.csv"
        result = runner.invoke(
            app,
            [
                "unmask",
                str(cfg_path),
                str(tmp_path / "masked.csv"),
                "--table",
                "accounts",
                "--output",
                str(out),
            ],
        )
        assert result.exit_code == 0, result.output

    def test_unknown_table_exits_usage(self, tmp_path: Path) -> None:
        cfg_path = _run_mask(tmp_path)
        result = runner.invoke(
            app,
            ["unmask", str(cfg_path), str(tmp_path / "masked.csv"), "--table", "nope"],
        )
        assert result.exit_code == EXIT_USAGE


class TestUnmaskVaultError:
    """The CLI must map typed VaultError to EXIT_USAGE, not EXIT_RUNTIME."""

    def _minimal_setup(self, tmp_path: Path) -> tuple[Path, Path, Path]:
        """Return (cfg_path, masked_path, vault_path) with minimum valid inputs."""
        src = tmp_path / "accounts.csv"
        pd.DataFrame({"ssn": ["123-45-6789"]}).to_csv(src, index=False)
        cfg = {
            "version": 1,
            "global_settings": {"seed": 42},
            "sources": {"accounts": {"type": "file", "format": "csv", "path": str(src)}},
            "tables": [
                {
                    "name": "accounts",
                    "columns": [
                        {
                            "name": "ssn",
                            "strategy": "fpe",
                            "namespace": "ssn_identity",
                            "provider_config": {"charset": "digits"},
                        }
                    ],
                }
            ],
            "targets": {
                "accounts": {
                    "type": "file",
                    "format": "csv",
                    "path": str(tmp_path / "masked.csv"),
                }
            },
        }
        cfg_path = tmp_path / "pipeline.yaml"
        cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

        masked = tmp_path / "masked.csv"
        masked.write_text("ssn\n999-00-1234\n", encoding="utf-8")

        # dummy vault file -- just needs to exist for Typer's exists=True check
        vault_path = tmp_path / "vault.bin"
        vault_path.write_bytes(b"dummy")

        return cfg_path, masked, vault_path

    def test_vault_protocol_version_mismatch_exits_usage(
        self, tmp_path: Path
    ) -> None:
        from decoy_engine import VaultError

        cfg_path, masked, vault_path = self._minimal_setup(tmp_path)

        def _raise(*_args: object, **_kwargs: object) -> None:
            raise VaultError(
                code="vault_protocol_version_mismatch",
                message="vault seed_protocol_version=5 does not match engine version=6",
            )

        with patch("decoy_engine.unmask_pipeline", side_effect=_raise):
            result = runner.invoke(
                app,
                [
                    "unmask",
                    str(cfg_path),
                    str(masked),
                    "--vault",
                    str(vault_path),
                ],
            )

        assert result.exit_code == EXIT_USAGE, (
            f"Expected EXIT_USAGE ({EXIT_USAGE}), got {result.exit_code}. "
            f"output={result.output!r}"
        )
        combined = (result.output or "") + (result.stderr if hasattr(result, "stderr") else "")
        assert "version" in combined.lower() or "mismatch" in combined.lower(), (
            f"Expected version/mismatch wording in output, got: {combined!r}"
        )
        assert "re-mask" in combined.lower() or "engine" in combined.lower(), (
            f"Expected migration hint in output, got: {combined!r}"
        )

    def test_vault_protocol_version_mismatch_json_exits_usage(
        self, tmp_path: Path
    ) -> None:
        from decoy_engine import VaultError

        cfg_path, masked, vault_path = self._minimal_setup(tmp_path)

        def _raise(*_args: object, **_kwargs: object) -> None:
            raise VaultError(
                code="vault_protocol_version_mismatch",
                message="vault seed_protocol_version=5 does not match engine version=6",
            )

        with patch("decoy_engine.unmask_pipeline", side_effect=_raise):
            result = runner.invoke(
                app,
                [
                    "unmask",
                    str(cfg_path),
                    str(masked),
                    "--vault",
                    str(vault_path),
                    "--json",
                ],
            )

        assert result.exit_code == EXIT_USAGE, (
            f"Expected EXIT_USAGE ({EXIT_USAGE}), got {result.exit_code}. "
            f"output={result.output!r}"
        )
        payload = json.loads(result.output)
        assert payload["status"] == "error"
        assert "version" in payload["error"].lower() or "mismatch" in payload["error"].lower(), (
            f"Expected version/mismatch in JSON error, got: {payload['error']!r}"
        )

    def test_other_vault_error_code_exits_usage(
        self, tmp_path: Path
    ) -> None:
        from decoy_engine import VaultError

        cfg_path, masked, vault_path = self._minimal_setup(tmp_path)

        def _raise(*_args: object, **_kwargs: object) -> None:
            raise VaultError(
                code="vault_decrypt_failed",
                message="AEAD decryption failed; wrong seed or corrupted vault",
            )

        with patch("decoy_engine.unmask_pipeline", side_effect=_raise):
            result = runner.invoke(
                app,
                [
                    "unmask",
                    str(cfg_path),
                    str(masked),
                    "--vault",
                    str(vault_path),
                ],
            )

        assert result.exit_code == EXIT_USAGE, (
            f"Expected EXIT_USAGE ({EXIT_USAGE}) for vault_decrypt_failed, "
            f"got {result.exit_code}. output={result.output!r}"
        )
