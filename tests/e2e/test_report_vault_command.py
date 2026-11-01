"""`decoy report vault` e2e tests (relocated from `vault info`, S4b).

Creates a real vault via `decoy run --vault`, then exercises the
`decoy report vault` command: happy path, --json envelope, and the
error paths. The vault is keyed by the mask secret (engine 0.17.0), never the seed.
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
from tests.keyed_secret import TEST_MASK_SECRET_BYTES, TEST_MASK_SECRET_REF

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
        "version": 2,
        "global_settings": {"seed": 42, "mask_secret_ref": TEST_MASK_SECRET_REF},
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
def vault_setup(tmp_path: Path, mask_secret: str):
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
            app, ["report", "vault", str(vault), "--config", str(cfg)]
        )
        assert result.exit_code == 0, result.output
        assert "entries" in result.output or "OK" in result.output

    def test_namespaces_reported(self, vault_setup) -> None:
        cfg, vault = vault_setup
        result = runner.invoke(
            app, ["report", "vault", str(vault), "--config", str(cfg)]
        )
        assert result.exit_code == 0, result.output
        # The namespace we declared is "email_ns"
        assert "email_ns" in result.output

    def test_json_envelope_keys(self, vault_setup) -> None:
        cfg, vault = vault_setup
        result = runner.invoke(
            app, ["report", "vault", str(vault), "--config", str(cfg), "--json"]
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output.strip())
        assert payload["command"] == "report vault"
        assert payload["status"] == "ok"
        assert payload["vault"] == str(vault)
        assert isinstance(payload["entries"], int) and payload["entries"] > 0
        assert isinstance(payload["namespaces"], list) and len(payload["namespaces"]) > 0
        assert "ambiguous_dropped" in payload

    def test_quiet_exits_0(self, vault_setup) -> None:
        cfg, vault = vault_setup
        result = runner.invoke(
            app, ["report", "vault", str(vault), "--config", str(cfg), "--quiet"]
        )
        assert result.exit_code == 0
        # quiet mode produces no stdout
        assert result.output.strip() == ""


# A second throwaway secret, distinct from tests/keyed_secret.py's; it is a canary too.
_OTHER_SECRET_ENV = "DECOY_TEST_OTHER_SECRET"
_OTHER_SECRET_BYTES = b"decoy-test-only-other-key-000032"


def _variant(cfg: Path, tmp_path: Path, name: str, **global_settings: object) -> Path:
    """The vault's own config with `global_settings` keys replaced (None deletes one)."""
    data = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    for key, value in global_settings.items():
        if value is None:
            data["global_settings"].pop(key, None)
        else:
            data["global_settings"][key] = value
    out = tmp_path / name
    out.write_text(yaml.safe_dump(data), encoding="utf-8")
    return out


def _assert_no_secret_bytes(text: str) -> None:
    for secret in (TEST_MASK_SECRET_BYTES, _OTHER_SECRET_BYTES):
        assert secret.hex() not in text
        assert secret.decode() not in text


class TestVaultInfoErrors:
    def test_wrong_secret_exits_usage_and_right_secret_opens(
        self, vault_setup, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The mask secret keys the vault: the same config opens it under the secret the run
        used and refuses it under another. A report vault that ignored the secret could not
        tell the two configs apart, so one half of this test would fail."""
        cfg, vault = vault_setup
        monkeypatch.setenv(_OTHER_SECRET_ENV, _OTHER_SECRET_BYTES.hex())
        wrong = _variant(cfg, tmp_path, "wrong.yaml", mask_secret_ref=f"env:{_OTHER_SECRET_ENV}")

        right_result = runner.invoke(app, ["report", "vault", str(vault), "--config", str(cfg)])
        assert right_result.exit_code == 0, right_result.output
        result = runner.invoke(app, ["report", "vault", str(vault), "--config", str(wrong)])
        assert result.exit_code == EXIT_USAGE, result.output
        assert "vault_key_mismatch" in result.output
        assert "Traceback" not in result.output
        _assert_no_secret_bytes(result.output)

    def test_wrong_secret_json_error_envelope(
        self, vault_setup, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg, vault = vault_setup
        monkeypatch.setenv(_OTHER_SECRET_ENV, _OTHER_SECRET_BYTES.hex())
        wrong = _variant(cfg, tmp_path, "wrong2.yaml", mask_secret_ref=f"env:{_OTHER_SECRET_ENV}")
        result = runner.invoke(
            app, ["report", "vault", str(vault), "--config", str(wrong), "--json"]
        )
        assert result.exit_code == EXIT_USAGE
        payload = json.loads(result.output.strip())
        assert payload["command"] == "report vault"
        assert payload["status"] == "error"
        assert payload["error"].startswith("vault_key_mismatch:")
        _assert_no_secret_bytes(result.output)

    def test_the_seed_no_longer_keys_the_vault(self, vault_setup, tmp_path: Path) -> None:
        """Engine 0.17.0 keys the vault with the mask secret alone; the public seed is not
        key material, so a different seed under the same secret still opens it."""
        cfg, vault = vault_setup
        other_seed = _variant(cfg, tmp_path, "other_seed.yaml", seed=99)
        result = runner.invoke(app, ["report", "vault", str(vault), "--config", str(other_seed)])
        assert result.exit_code == 0, result.output
        assert "email_ns" in result.output

    @pytest.mark.parametrize("json_mode", [False, True], ids=["console", "json"])
    def test_no_secret_refuses_with_the_registered_code(
        self, vault_setup, tmp_path: Path, json_mode: bool
    ) -> None:
        from decoy._mask_secret_guidance import CODE, REPORT_VAULT

        cfg, vault = vault_setup
        no_secret = _variant(cfg, tmp_path, "no_secret.yaml", mask_secret_ref=None)
        args = ["report", "vault", str(vault), "--config", str(no_secret)]
        result = runner.invoke(app, args + (["--json"] if json_mode else []))
        assert result.exit_code == EXIT_USAGE, result.output
        assert CODE == "keyed_strategy_requires_secret"
        if json_mode:
            payload = json.loads(result.output.strip())
            assert payload["status"] == "error"
            assert payload["error"] == REPORT_VAULT
        else:
            assert " ".join(REPORT_VAULT.split()) in " ".join(result.output.split())
        assert "vault_key_mismatch" not in result.output
        _assert_no_secret_bytes(result.output)

    def test_an_unkeyed_config_with_no_secret_still_refuses(
        self, vault_setup, tmp_path: Path
    ) -> None:
        """A config with no keyed column admits no secret, but a vault is always keyed: the
        command refuses with the fixed message instead of reaching load_vault with no key."""
        from decoy._mask_secret_guidance import REPORT_VAULT

        cfg, vault = vault_setup
        unkeyed = yaml.safe_load(cfg.read_text(encoding="utf-8"))
        unkeyed["global_settings"].pop("mask_secret_ref")
        unkeyed["tables"][0]["columns"] = [{"name": "email", "strategy": "redact"}]
        path = tmp_path / "unkeyed.yaml"
        path.write_text(yaml.safe_dump(unkeyed), encoding="utf-8")
        result = runner.invoke(app, ["report", "vault", str(vault), "--config", str(path), "--json"])
        assert result.exit_code == EXIT_USAGE, result.output
        assert json.loads(result.output.strip())["error"] == REPORT_VAULT

    def test_a_raw_secret_pasted_as_the_ref_is_refused_without_echo(
        self, vault_setup, tmp_path: Path
    ) -> None:
        """An operator who pastes the secret itself where the reference belongs gets a usage
        error that never repeats the value."""
        cfg, vault = vault_setup
        pasted = _variant(cfg, tmp_path, "pasted.yaml", mask_secret_ref=_OTHER_SECRET_BYTES.hex())
        for extra in ([], ["--json"]):
            result = runner.invoke(
                app, ["report", "vault", str(vault), "--config", str(pasted), *extra]
            )
            assert result.exit_code == EXIT_USAGE, result.output
            assert "Traceback" not in result.output
            _assert_no_secret_bytes(result.output)


class TestVaultInfoInstallLine:
    def test_engine_install_line_keeps_its_bracketed_extra(
        self, vault_setup, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # load_vault's vault_crypto_not_installed message ends in
        # `pip install 'decoy-engine[vault]'`; printed through Rich markup,
        # `[vault]` is parsed as a tag and disappears.
        import sys

        cfg, vault = vault_setup
        monkeypatch.setitem(sys.modules, "cryptography.fernet", None)
        result = runner.invoke(app, ["report", "vault", str(vault), "--config", str(cfg)])
        assert result.exit_code == EXIT_USAGE, result.output
        flat = " ".join(result.output.split())
        assert "vault_crypto_not_installed" in flat, flat
        assert "decoy-engine[vault]" in flat, flat
