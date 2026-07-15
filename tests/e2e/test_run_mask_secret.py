"""End-to-end tests for `decoy run --mask-secret` (DE-02 Option B, 2026-07-15).

`--mask-secret` sets `global_settings.mask_secret_ref` for a run, the same
slot the pipeline YAML can set directly. It feeds the engine's DE-02
KeyProvider on both the plain (`run_pipeline`) and `--chunked` paths, is
independent of `--master-key` (which is generation-only), and must not
silently override an already-configured YAML `mask_secret_ref`.

See also: tests/e2e/test_unmask_command.py (the DE-02 job_seed-fallback
"reversed_unverified" status this flag is meant to upgrade away from),
tests/e2e/test_run_chunked.py (the chunked byte-parity contract this
flag must not break).
"""

from __future__ import annotations

import secrets
from pathlib import Path

import pandas as pd
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_USAGE

runner = CliRunner()

# Two distinct >=32-byte secrets (hex-encoded per keyprovider's decode rule).
_SECRET_A = secrets.token_hex(32)
_SECRET_B = secrets.token_hex(32)


def _mask_pipeline(tmp_path: Path, *, mask_secret_ref: str | None = None, rows: int = 50) -> Path:
    src = tmp_path / "accounts.csv"
    pd.DataFrame(
        {
            "ssn": [f"{i:09d}" for i in range(rows)],
            "email": [f"user{i}@example.com" for i in range(rows)],
        }
    ).to_csv(src, index=False)
    global_settings = {"seed": 42}
    if mask_secret_ref is not None:
        global_settings["mask_secret_ref"] = mask_secret_ref
    cfg = {
        "version": 1,
        "global_settings": global_settings,
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


def _mixed_pipeline(tmp_path: Path, *, mask_secret_ref: str | None = None) -> Path:
    """Generate table (employees) + mask table (accounts, fpe-keyed) so
    generation and masking output can be checked for independence."""
    src = tmp_path / "accounts.csv"
    pd.DataFrame({"ssn": [f"{i:09d}" for i in range(20)]}).to_csv(src, index=False)
    global_settings = {"seed": 42}
    if mask_secret_ref is not None:
        global_settings["mask_secret_ref"] = mask_secret_ref
    cfg = {
        "version": 1,
        "global_settings": global_settings,
        "sources": {"accounts": {"type": "file", "format": "csv", "path": str(src)}},
        "tables": [
            {
                "name": "employees",
                "row_count": 10,
                "generate_columns": [
                    {"name": "first_name", "type": "faker", "faker_type": "first_name"},
                ],
            },
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
            },
        ],
        "targets": {
            "employees": {
                "type": "file",
                "format": "csv",
                "path": str(tmp_path / "employees.csv"),
            },
            "accounts": {
                "type": "file",
                "format": "csv",
                "path": str(tmp_path / "accounts_out.csv"),
            },
        },
    }
    p = tmp_path / "pipeline.yaml"
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return p


class TestMaskSecretKeyedOutput:
    def test_keyed_output_differs_from_unkeyed_run(self, tmp_path: Path) -> None:
        (tmp_path / "unkeyed").mkdir(exist_ok=True)
        unkeyed_cfg = _mask_pipeline(tmp_path / "unkeyed")
        result = runner.invoke(app, ["run", str(unkeyed_cfg)])
        assert result.exit_code == 0, result.output
        unkeyed_out = (tmp_path / "unkeyed" / "out.csv").read_bytes()

        (tmp_path / "keyed").mkdir(exist_ok=True)
        keyed_cfg = _mask_pipeline(tmp_path / "keyed")
        result = runner.invoke(
            app,
            ["run", str(keyed_cfg), "--mask-secret", "env:DECOY_MASK_SECRET"],
            env={"DECOY_MASK_SECRET": _SECRET_A},
        )
        assert result.exit_code == 0, result.output
        keyed_out = (tmp_path / "keyed" / "out.csv").read_bytes()

        assert keyed_out != unkeyed_out

    def test_same_secret_is_byte_identical_across_runs(self, tmp_path: Path) -> None:
        (tmp_path / "run1").mkdir()
        (tmp_path / "run2").mkdir()
        cfg1 = _mask_pipeline(tmp_path / "run1")
        cfg2 = _mask_pipeline(tmp_path / "run2")

        r1 = runner.invoke(
            app,
            ["run", str(cfg1), "--mask-secret", "env:DECOY_MASK_SECRET"],
            env={"DECOY_MASK_SECRET": _SECRET_A},
        )
        assert r1.exit_code == 0, r1.output
        r2 = runner.invoke(
            app,
            ["run", str(cfg2), "--mask-secret", "env:DECOY_MASK_SECRET"],
            env={"DECOY_MASK_SECRET": _SECRET_A},
        )
        assert r2.exit_code == 0, r2.output

        out1 = (tmp_path / "run1" / "out.csv").read_bytes()
        out2 = (tmp_path / "run2" / "out.csv").read_bytes()
        assert out1 == out2

    def test_different_secrets_produce_different_output(self, tmp_path: Path) -> None:
        (tmp_path / "run1").mkdir()
        (tmp_path / "run2").mkdir()
        cfg1 = _mask_pipeline(tmp_path / "run1")
        cfg2 = _mask_pipeline(tmp_path / "run2")

        r1 = runner.invoke(
            app,
            ["run", str(cfg1), "--mask-secret", "env:DECOY_MASK_SECRET"],
            env={"DECOY_MASK_SECRET": _SECRET_A},
        )
        assert r1.exit_code == 0, r1.output
        r2 = runner.invoke(
            app,
            ["run", str(cfg2), "--mask-secret", "env:DECOY_MASK_SECRET"],
            env={"DECOY_MASK_SECRET": _SECRET_B},
        )
        assert r2.exit_code == 0, r2.output

        out1 = (tmp_path / "run1" / "out.csv").read_bytes()
        out2 = (tmp_path / "run2" / "out.csv").read_bytes()
        assert out1 != out2


class TestMasterKeyMaskSecretIndependence:
    """--master-key (generation) and --mask-secret (masking) are two
    independent secrets; changing one must not perturb the other's output."""

    def _run(self, tmp_path: Path, *, master_key: str | None, mask_secret: str | None) -> Path:
        d = tmp_path / f"m{master_key}_s{mask_secret}"
        d.mkdir()
        cfg = _mixed_pipeline(d)
        args = ["run", str(cfg)]
        env = {}
        if master_key is not None:
            args += ["--master-key", master_key, "--key-label", "mask-secret-independence-test"]
        if mask_secret is not None:
            args += ["--mask-secret", "env:DECOY_MASK_SECRET"]
            env["DECOY_MASK_SECRET"] = mask_secret
        result = runner.invoke(app, args, env=env)
        assert result.exit_code == 0, result.output
        return d

    def test_changing_master_key_only_changes_generation_output(self, tmp_path: Path) -> None:
        key_a = secrets.token_hex(32)
        key_b = secrets.token_hex(32)

        d1 = self._run(tmp_path, master_key=key_a, mask_secret=_SECRET_A)
        d2 = self._run(tmp_path, master_key=key_b, mask_secret=_SECRET_A)

        gen1 = (d1 / "employees.csv").read_bytes()
        gen2 = (d2 / "employees.csv").read_bytes()
        assert gen1 != gen2, "different --master-key must change generation output"

        mask1 = (d1 / "accounts_out.csv").read_bytes()
        mask2 = (d2 / "accounts_out.csv").read_bytes()
        assert mask1 == mask2, "--master-key must not affect masking output"

    def test_changing_mask_secret_only_changes_masking_output(self, tmp_path: Path) -> None:
        master_key = secrets.token_hex(32)

        d1 = self._run(tmp_path, master_key=master_key, mask_secret=_SECRET_A)
        d2 = self._run(tmp_path, master_key=master_key, mask_secret=_SECRET_B)

        mask1 = (d1 / "accounts_out.csv").read_bytes()
        mask2 = (d2 / "accounts_out.csv").read_bytes()
        assert mask1 != mask2, "different --mask-secret must change masking output"

        gen1 = (d1 / "employees.csv").read_bytes()
        gen2 = (d2 / "employees.csv").read_bytes()
        assert gen1 == gen2, "--mask-secret must not affect generation output"


class TestMaskSecretUsageErrors:
    def test_flag_and_yaml_ref_both_set_exits_usage(self, tmp_path: Path) -> None:
        cfg = _mask_pipeline(tmp_path, mask_secret_ref="env:DECOY_MASK_SECRET")
        result = runner.invoke(
            app,
            ["run", str(cfg), "--mask-secret", "env:DECOY_MASK_SECRET"],
            env={"DECOY_MASK_SECRET": _SECRET_A},
        )
        assert result.exit_code == EXIT_USAGE, (
            f"expected EXIT_USAGE ({EXIT_USAGE}), got {result.exit_code}. output={result.output!r}"
        )
        assert "mask_secret_ref" in result.output

    def test_missing_env_var_exits_usage(self, tmp_path: Path) -> None:
        cfg = _mask_pipeline(tmp_path)
        result = runner.invoke(
            app,
            ["run", str(cfg), "--mask-secret", "env:DECOY_MASK_SECRET_DOES_NOT_EXIST"],
            env={},
        )
        assert result.exit_code == EXIT_USAGE, (
            f"expected EXIT_USAGE ({EXIT_USAGE}), got {result.exit_code}. output={result.output!r}"
        )

    def test_unreadable_file_ref_exits_usage(self, tmp_path: Path) -> None:
        cfg = _mask_pipeline(tmp_path)
        missing_path = tmp_path / "does_not_exist_secret.txt"
        result = runner.invoke(
            app,
            ["run", str(cfg), "--mask-secret", f"file:{missing_path}"],
        )
        assert result.exit_code == EXIT_USAGE, (
            f"expected EXIT_USAGE ({EXIT_USAGE}), got {result.exit_code}. output={result.output!r}"
        )

    def test_json_mode_reports_usage_error(self, tmp_path: Path) -> None:
        import json

        cfg = _mask_pipeline(tmp_path)
        result = runner.invoke(
            app,
            [
                "run",
                str(cfg),
                "--mask-secret",
                "env:DECOY_MASK_SECRET_DOES_NOT_EXIST",
                "--json",
            ],
            env={},
        )
        assert result.exit_code == EXIT_USAGE
        payload = json.loads(result.output)
        assert payload["status"] == "error"


class TestMaskSecretChunked:
    def test_chunked_run_respects_mask_secret(self, tmp_path: Path) -> None:
        (tmp_path / "plain").mkdir()
        (tmp_path / "chunked").mkdir()
        plain_cfg = _mask_pipeline(tmp_path / "plain", rows=200)
        chunked_cfg = _mask_pipeline(tmp_path / "chunked", rows=200)

        r_plain = runner.invoke(
            app,
            ["run", str(plain_cfg), "--mask-secret", "env:DECOY_MASK_SECRET"],
            env={"DECOY_MASK_SECRET": _SECRET_A},
        )
        assert r_plain.exit_code == 0, r_plain.output

        r_chunked = runner.invoke(
            app,
            [
                "run",
                str(chunked_cfg),
                "--chunked",
                "--chunk-size",
                "37",
                "--mask-secret",
                "env:DECOY_MASK_SECRET",
            ],
            env={"DECOY_MASK_SECRET": _SECRET_A},
        )
        assert r_chunked.exit_code == 0, r_chunked.output

        plain_out = (tmp_path / "plain" / "out.csv").read_bytes()
        chunked_out = (tmp_path / "chunked" / "out.csv").read_bytes()
        assert plain_out == chunked_out

        # Sanity: the chunked+keyed run must differ from an unkeyed run,
        # proving --mask-secret was actually consulted on the chunked path
        # (not silently ignored while still passing the byte-parity check
        # above for an unrelated reason).
        (tmp_path / "chunked_unkeyed").mkdir()
        unkeyed_cfg = _mask_pipeline(tmp_path / "chunked_unkeyed", rows=200)
        r_unkeyed = runner.invoke(
            app,
            ["run", str(unkeyed_cfg), "--chunked", "--chunk-size", "37"],
        )
        assert r_unkeyed.exit_code == 0, r_unkeyed.output
        unkeyed_out = (tmp_path / "chunked_unkeyed" / "out.csv").read_bytes()
        assert unkeyed_out != chunked_out
