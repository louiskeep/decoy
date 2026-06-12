"""`decoy run --vault` + `decoy unmask --vault` (deferred follow-up 1).

The vault records (namespace, masked) -> source for `vault: true`
columns at mask time, encrypted under the config's seed, so one-way
strategies recover at unmask time. Opt-in twice: the column flag AND
the --vault path.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_USAGE

pytest.importorskip("cryptography")

runner = CliRunner()


def _pipeline(tmp_path: Path, columns: list[dict], rows: int = 50) -> Path:
    src = tmp_path / "in.csv"
    pd.DataFrame(
        {
            "email": [f"user{i}@example.com" for i in range(rows)],
            "name": [f"Person {i}" for i in range(rows)],
        }
    ).to_csv(src, index=False)
    cfg = {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {"accounts": {"type": "file", "format": "csv", "path": str(src)}},
        "tables": [{"name": "accounts", "columns": columns}],
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


_VAULTED = [
    {"name": "email", "strategy": "hash", "namespace": "email_ns", "vault": True},
    {"name": "name", "strategy": "redact"},
]


class TestVaultRoundTrip:
    def test_run_writes_vault_and_unmask_recovers(self, tmp_path: Path) -> None:
        cfg = _pipeline(tmp_path, _VAULTED)
        vault = tmp_path / "vault.bin"
        result = runner.invoke(app, ["run", str(cfg), "--vault", str(vault)])
        assert result.exit_code == 0, result.output
        assert vault.exists() and vault.stat().st_size > 0

        masked = pd.read_csv(tmp_path / "out.csv", dtype=str)
        assert masked["email"].tolist() != [f"user{i}@example.com" for i in range(50)]

        out = tmp_path / "recovered.csv"
        result = runner.invoke(
            app,
            [
                "unmask",
                str(cfg),
                str(tmp_path / "out.csv"),
                "--vault",
                str(vault),
                "--output",
                str(out),
            ],
        )
        assert result.exit_code == 0, result.output
        recovered = pd.read_csv(out, dtype=str)
        assert recovered["email"].tolist() == [
            f"user{i}@example.com" for i in range(50)
        ]
        assert "vault-reversed" in result.output

    def test_chunked_run_writes_equivalent_vault(self, tmp_path: Path) -> None:
        cfg = _pipeline(tmp_path, _VAULTED)
        vault = tmp_path / "vault.bin"
        result = runner.invoke(
            app,
            ["run", str(cfg), "--chunked", "--chunk-size", "7", "--vault", str(vault)],
        )
        assert result.exit_code == 0, result.output

        out = tmp_path / "recovered.csv"
        result = runner.invoke(
            app,
            [
                "unmask",
                str(cfg),
                str(tmp_path / "out.csv"),
                "--vault",
                str(vault),
                "--output",
                str(out),
            ],
        )
        assert result.exit_code == 0, result.output
        recovered = pd.read_csv(out, dtype=str)
        assert recovered["email"].tolist() == [
            f"user{i}@example.com" for i in range(50)
        ]


class TestVaultUsageErrors:
    def test_vault_without_vaulted_columns_exits_usage(self, tmp_path: Path) -> None:
        cfg = _pipeline(
            tmp_path, [{"name": "email", "strategy": "hash", "namespace": "n"}]
        )
        result = runner.invoke(
            app, ["run", str(cfg), "--vault", str(tmp_path / "v.bin")]
        )
        assert result.exit_code == EXIT_USAGE
        assert "vault: true" in result.output

    def test_unmask_without_vault_reports_irreversible(self, tmp_path: Path) -> None:
        cfg = _pipeline(tmp_path, _VAULTED)
        assert runner.invoke(app, ["run", str(cfg)]).exit_code == 0
        result = runner.invoke(app, ["unmask", str(cfg), str(tmp_path / "out.csv")])
        assert result.exit_code == 0, result.output
        assert "0 column(s) reversed" in result.output

    def test_unmask_with_wrong_seed_config_exits_usage(self, tmp_path: Path) -> None:
        cfg = _pipeline(tmp_path, _VAULTED)
        vault = tmp_path / "vault.bin"
        assert (
            runner.invoke(app, ["run", str(cfg), "--vault", str(vault)]).exit_code == 0
        )
        # Same config shape, different seed: the vault must not decrypt.
        wrong = yaml.safe_load(cfg.read_text(encoding="utf-8"))
        wrong["global_settings"]["seed"] = 99
        wrong_path = tmp_path / "wrong.yaml"
        wrong_path.write_text(yaml.safe_dump(wrong), encoding="utf-8")
        result = runner.invoke(
            app,
            [
                "unmask",
                str(wrong_path),
                str(tmp_path / "out.csv"),
                "--vault",
                str(vault),
            ],
        )
        assert result.exit_code == EXIT_USAGE
        assert "vault_key_mismatch" in result.output
