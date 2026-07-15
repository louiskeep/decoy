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

import json
import secrets
import sys
from contextlib import contextmanager
from importlib.abc import MetaPathFinder
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

_KEYPROVIDER_MOD = "decoy_engine.keyprovider"


class _BlockKeyprovider(MetaPathFinder):
    """Meta-path finder that makes `import decoy_engine.keyprovider` raise, to
    simulate a pre-DE-02 engine that has no keyprovider module. Returns None
    for every other module so normal imports are untouched."""

    def find_spec(self, fullname, path, target=None):
        if fullname == _KEYPROVIDER_MOD:
            raise ModuleNotFoundError(f"No module named {_KEYPROVIDER_MOD!r}", name=fullname)
        return None


@contextmanager
def _simulate_pre_de02_engine():
    """Make a FRESH `import decoy_engine.keyprovider` raise, to model a
    pre-DE-02 engine -- while leaving the already-loaded engine intact.

    Subtlety: the whole engine module-level chain imports keyprovider
    (decoy_engine/__init__ -> ... -> execution/_sequential), so we first force
    `import decoy_engine` to guarantee that entire graph is cached. Only THEN
    do we evict `decoy_engine.keyprovider` from sys.modules and install a
    raising finder. That makes the block SURGICAL: cached engine modules keep
    their bound names and keep working, and only a fresh runtime import of
    keyprovider (the CLI's fail-closed probe) hits the finder. Without the
    warm-up, evicting keyprovider would cascade and break the engine's own
    import for an unrelated reason, and the test would pass for the wrong
    reason regardless of pytest ordering.

    Both the finder and the sys.modules entry are restored in the finally so
    nothing leaks into other tests. Dennis verified the guard manually with
    this same meta_path block.
    """
    import decoy_engine  # noqa: F401 -- force the full module-level chain to cache

    finder = _BlockKeyprovider()
    saved = sys.modules.pop(_KEYPROVIDER_MOD, None)
    sys.meta_path.insert(0, finder)
    try:
        yield
    finally:
        try:
            sys.meta_path.remove(finder)
        except ValueError:
            pass
        if saved is not None:
            sys.modules[_KEYPROVIDER_MOD] = saved


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

    def test_empty_ref_exits_usage(self, tmp_path: Path) -> None:
        """`--mask-secret ''` (explicit empty) must be a usage error, never a
        silent fall-through to an unkeyed (job_seed) run. Regression guard for
        the truthiness fail-open."""
        cfg = _mask_pipeline(tmp_path)
        result = runner.invoke(app, ["run", str(cfg), "--mask-secret", ""])
        assert result.exit_code == EXIT_USAGE, (
            f"expected EXIT_USAGE ({EXIT_USAGE}), got {result.exit_code}. output={result.output!r}"
        )
        # The masked output must NOT have been written as an unkeyed run.
        assert not (tmp_path / "out.csv").exists(), "empty --mask-secret must not produce output"

    def test_empty_yaml_ref_exits_usage_no_output(self, tmp_path: Path) -> None:
        """A configured-but-empty YAML `mask_secret_ref: ""` (no flag) on a
        keyed strategy must be a usage error, NOT a silent unkeyed run.

        Regression for the presence-vs-truthiness fail-open: the engine's
        resolvers treat "" as no-secret, so a truthiness gate would let the run
        emit UNKEYED output pre-GA (exit 0, out.csv written). The CLI must key
        off PRESENCE and reject the empty ref before any masking."""
        cfg = _mask_pipeline(tmp_path, mask_secret_ref="")  # empty YAML ref, no flag
        result = runner.invoke(app, ["run", str(cfg)])
        assert result.exit_code == EXIT_USAGE, (
            f"empty YAML mask_secret_ref must be refused with EXIT_USAGE ({EXIT_USAGE}); "
            f"got {result.exit_code}. output={result.output!r}"
        )
        assert not (tmp_path / "out.csv").exists(), (
            "an empty mask_secret_ref must not fall through to an unkeyed run"
        )

    def test_malformed_ref_exits_usage(self, tmp_path: Path) -> None:
        """A ref that is neither env: nor file: (e.g. a raw secret pasted as
        the value) is a usage error before the engine ever sees it."""
        cfg = _mask_pipeline(tmp_path)
        result = runner.invoke(app, ["run", str(cfg), "--mask-secret", "not-a-ref-shape"])
        assert result.exit_code == EXIT_USAGE, (
            f"expected EXIT_USAGE ({EXIT_USAGE}), got {result.exit_code}. output={result.output!r}"
        )

    def test_malformed_ref_does_not_disclose_secret_value(self, tmp_path: Path) -> None:
        """If a user passes a RAW secret as --mask-secret (malformed, since it
        lacks env:/file:), the error must NOT echo the value anywhere -- not on
        stdout/stderr, not in the --json error payload. It may be a real secret."""
        raw_secret = secrets.token_hex(32)  # 64 hex chars, no env:/file: prefix
        cfg = _mask_pipeline(tmp_path)

        result = runner.invoke(app, ["run", str(cfg), "--mask-secret", raw_secret])
        assert result.exit_code == EXIT_USAGE, (
            f"expected EXIT_USAGE ({EXIT_USAGE}), got {result.exit_code}. output={result.output!r}"
        )
        assert raw_secret not in result.output, (
            "the raw --mask-secret value must never appear in CLI output"
        )

        # Same guarantee through the machine-readable --json envelope.
        (tmp_path / "json_run").mkdir(exist_ok=True)
        cfg_json = _mask_pipeline(tmp_path / "json_run")
        result_json = runner.invoke(
            app, ["run", str(cfg_json), "--mask-secret", raw_secret, "--json"]
        )
        assert result_json.exit_code == EXIT_USAGE
        assert raw_secret not in result_json.output, (
            "the raw --mask-secret value must never appear in the --json payload"
        )
        payload = json.loads(result_json.output)
        assert payload["status"] == "error"
        assert raw_secret not in payload["error"]

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


# A 32-byte marker that stands in for real secret material pasted into the
# YAML as the WRONG type. If the pre-Pydantic guard is missing, Pydantic's
# ValidationError echoes this via `input_value`, disclosing it.
_SECRET_MARKER = "S3CRET_MATERIAL_0123456789ABCDEF"


class TestMaskSecretWrongTypeYaml:
    """A wrong-type YAML `mask_secret_ref` must NOT reach Pydantic (whose error
    echoes the offending value = the secret). The CLI pre-validates the raw ref
    before model_validate and refuses with a redacted usage error. Root fix for
    the whole non-str class, not just the list case."""

    @staticmethod
    def _assert_refused_and_redacted(result, marker: str, out_csv: Path) -> None:
        assert result.exit_code == EXIT_USAGE, (
            f"wrong-type mask_secret_ref must be EXIT_USAGE ({EXIT_USAGE}); "
            f"got {result.exit_code}. output={result.output!r}"
        )
        assert marker not in result.output, (
            f"the secret marker leaked into output: {result.output!r}"
        )
        assert not out_csv.exists(), "no output must be written on a refused run"

    def test_list_ref_plain_refused_and_redacted(self, tmp_path: Path) -> None:
        cfg = _mask_pipeline(tmp_path, mask_secret_ref=[_SECRET_MARKER])
        result = runner.invoke(app, ["run", str(cfg)])
        self._assert_refused_and_redacted(result, _SECRET_MARKER, tmp_path / "out.csv")

    def test_list_ref_json_refused_and_redacted(self, tmp_path: Path) -> None:
        cfg = _mask_pipeline(tmp_path, mask_secret_ref=[_SECRET_MARKER])
        result = runner.invoke(app, ["run", str(cfg), "--json"])
        assert result.exit_code == EXIT_USAGE
        assert _SECRET_MARKER not in result.output, "secret marker leaked into --json output"
        payload = json.loads(result.output)
        assert payload["status"] == "error"
        assert _SECRET_MARKER not in payload["error"], (
            "secret marker leaked into --json error field"
        )
        assert not (tmp_path / "out.csv").exists()

    def test_list_ref_verbose_refused_and_redacted(self, tmp_path: Path) -> None:
        cfg = _mask_pipeline(tmp_path, mask_secret_ref=[_SECRET_MARKER])
        result = runner.invoke(app, ["run", str(cfg), "--verbose"])
        # --verbose prints a traceback; the marker must still be nowhere in it.
        self._assert_refused_and_redacted(result, _SECRET_MARKER, tmp_path / "out.csv")

    def test_list_ref_chunked_refused_and_redacted(self, tmp_path: Path) -> None:
        cfg = _mask_pipeline(tmp_path, mask_secret_ref=[_SECRET_MARKER])
        result = runner.invoke(app, ["run", str(cfg), "--chunked", "--chunk-size", "17"])
        self._assert_refused_and_redacted(result, _SECRET_MARKER, tmp_path / "out.csv")

    def test_int_scalar_ref_refused_and_redacted(self, tmp_path: Path) -> None:
        """A non-string scalar (int) mask_secret_ref is also refused, redacted."""
        secret_int = 1234567890123456789
        cfg = _mask_pipeline(tmp_path, mask_secret_ref=secret_int)
        result = runner.invoke(app, ["run", str(cfg)])
        assert result.exit_code == EXIT_USAGE, (
            f"expected EXIT_USAGE ({EXIT_USAGE}), got {result.exit_code}. output={result.output!r}"
        )
        assert str(secret_int) not in result.output, "the int secret value leaked into output"
        assert not (tmp_path / "out.csv").exists()

    def test_int_scalar_ref_chunked_refused_and_redacted(self, tmp_path: Path) -> None:
        secret_int = 1234567890123456789
        cfg = _mask_pipeline(tmp_path, mask_secret_ref=secret_int)
        result = runner.invoke(app, ["run", str(cfg), "--chunked", "--chunk-size", "17"])
        assert result.exit_code == EXIT_USAGE
        assert str(secret_int) not in result.output
        assert not (tmp_path / "out.csv").exists()

    def test_non_dict_global_settings_refused_and_redacted(self, tmp_path: Path) -> None:
        """A `global_settings` that is itself a NON-DICT (e.g. a YAML list) is
        malformed AND could smuggle a `mask_secret_ref` value nested where the
        dict-path check (`_raw_gs.get("mask_secret_ref")`) can't see it --
        Pydantic's `ValidationError` would then echo that nested value in its
        `input_value` field, disclosing it. `run.py`'s pre-Pydantic guard
        (`if _raw_gs is not None and not isinstance(_raw_gs, dict)`) rejects
        this shape with a redacted `_MaskSecretUsageError` before
        `PipelineConfig.model_validate` ever sees it -- so this must exit
        EXIT_USAGE(1), NOT EXIT_RUNTIME(3), and the secret must never appear
        in `result.output` (stdout+stderr combined, which CliRunner captures)."""
        src = tmp_path / "accounts.csv"
        pd.DataFrame({"ssn": [f"{i:09d}" for i in range(5)]}).to_csv(src, index=False)
        # global_settings is a YAML LIST (not a mapping), with the secret
        # smuggled inside a nested dict item.
        raw_cfg = {
            "version": 1,
            "global_settings": [{"mask_secret_ref": [_SECRET_MARKER]}],
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
        cfg = tmp_path / "pipeline.yaml"
        cfg.write_text(yaml.safe_dump(raw_cfg), encoding="utf-8")

        result = runner.invoke(app, ["run", str(cfg)])
        assert result.exit_code == EXIT_USAGE, (
            f"non-dict global_settings must be EXIT_USAGE ({EXIT_USAGE}), not "
            f"EXIT_RUNTIME; got {result.exit_code}. output={result.output!r}"
        )
        assert _SECRET_MARKER not in result.output, (
            f"the secret nested inside non-dict global_settings leaked into "
            f"output: {result.output!r}"
        )
        assert not (tmp_path / "out.csv").exists(), (
            "no output must be written on a refused run"
        )


class TestMaskSecretYamlWorkflow:
    """The canonical documented workflow -- YAML sets
    `mask_secret_ref: "env:DECOY_MASK_SECRET"`, the secret is exported, and NO
    CLI flag is passed -- must work. This is the exact path that regressed when
    `--mask-secret` carried `envvar="DECOY_MASK_SECRET"` (Typer absorbed the
    exported secret as the flag value and tripped the both-set guard)."""

    def test_yaml_ref_with_exported_secret_no_flag_exits_zero(self, tmp_path: Path) -> None:
        (tmp_path / "keyed").mkdir()
        (tmp_path / "unkeyed").mkdir()
        keyed_cfg = _mask_pipeline(tmp_path / "keyed", mask_secret_ref="env:DECOY_MASK_SECRET")
        result = runner.invoke(
            app,
            ["run", str(keyed_cfg)],  # NO --mask-secret flag
            env={"DECOY_MASK_SECRET": _SECRET_A},
        )
        assert result.exit_code == 0, (
            "documented no-flag workflow (YAML mask_secret_ref + exported secret) "
            f"must exit 0; got {result.exit_code}. output={result.output!r}"
        )
        keyed_out = (tmp_path / "keyed" / "out.csv").read_bytes()

        # And it must actually be keyed (differs from an unkeyed run).
        unkeyed_cfg = _mask_pipeline(tmp_path / "unkeyed")
        assert runner.invoke(app, ["run", str(unkeyed_cfg)]).exit_code == 0
        unkeyed_out = (tmp_path / "unkeyed" / "out.csv").read_bytes()
        assert keyed_out != unkeyed_out

    def test_exported_env_var_is_not_absorbed_as_flag_value(self, tmp_path: Path) -> None:
        """With `--mask-secret`'s envvar removed, exporting DECOY_MASK_SECRET
        (no flag, no YAML ref) must have ZERO effect on the run -- the raw
        secret is not silently absorbed as the flag value and turned into a
        (malformed) mask_secret_ref."""
        (tmp_path / "with_env").mkdir()
        (tmp_path / "no_env").mkdir()
        cfg_with_env = _mask_pipeline(tmp_path / "with_env")
        cfg_no_env = _mask_pipeline(tmp_path / "no_env")

        r_env = runner.invoke(app, ["run", str(cfg_with_env)], env={"DECOY_MASK_SECRET": _SECRET_A})
        assert r_env.exit_code == 0, r_env.output
        r_noenv = runner.invoke(app, ["run", str(cfg_no_env)], env={})
        assert r_noenv.exit_code == 0, r_noenv.output

        # Byte-identical: the exported env var had no effect (not absorbed).
        assert (tmp_path / "with_env" / "out.csv").read_bytes() == (
            tmp_path / "no_env" / "out.csv"
        ).read_bytes()


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


class TestPreDE02EngineGuard:
    """Lock in the fail-closed engine-capability probe: when a mask secret is
    configured but the installed engine has no `decoy_engine.keyprovider`
    (a pre-DE-02 engine), the run is REFUSED before any masking, rather than
    silently emitting UNKEYED output. Security-relevant guard against silent
    fail-open. Both the plain and --chunked routes share the same up-front
    probe, so both are covered."""

    @staticmethod
    def _assert_refused_by_guard(result, out_csv: Path) -> None:
        """The result must be the GUARD's clean refusal, not an incidental
        crash. The guard emits its distinctive message and exits EXIT_USAGE;
        an engine crash under the block would emit nothing and exit RUNTIME.
        Asserting the message text is what makes this test FAIL if the probe is
        removed (a crash produces empty output, so 'keyprovider' is absent)."""
        assert result.exit_code == EXIT_USAGE, (
            f"expected the guard's EXIT_USAGE ({EXIT_USAGE}); got {result.exit_code}. "
            f"output={result.output!r}"
        )
        assert "keyprovider" in result.output and "UNKEYED" in result.output, (
            "expected the fail-closed guard's message (mentions the missing "
            f"keyprovider + UNKEYED output); got: {result.output!r}"
        )
        # Lock the remediation floor to DE-02's release marker so the guard's
        # advice cannot silently drift below the pyproject floor.
        assert "decoy-engine>=0.4.0" in result.output, (
            "guard should point operators at the DE-02 floor (decoy-engine>=0.4.0); "
            f"got: {result.output!r}"
        )
        # Refused BEFORE masking -> no output artifact leaked.
        assert not out_csv.exists(), "the run must be refused before writing any (unkeyed) output"

    def test_plain_run_refused_when_keyprovider_absent(self, tmp_path: Path) -> None:
        cfg = _mask_pipeline(tmp_path, mask_secret_ref="env:DECOY_MASK_SECRET")
        with _simulate_pre_de02_engine():
            result = runner.invoke(
                app,
                ["run", str(cfg)],  # YAML carries the ref; no flag needed
                env={"DECOY_MASK_SECRET": _SECRET_A},
            )
        self._assert_refused_by_guard(result, tmp_path / "out.csv")

    def test_chunked_run_refused_when_keyprovider_absent(self, tmp_path: Path) -> None:
        cfg = _mask_pipeline(tmp_path, mask_secret_ref="env:DECOY_MASK_SECRET")
        with _simulate_pre_de02_engine():
            result = runner.invoke(
                app,
                ["run", str(cfg), "--chunked", "--chunk-size", "37"],
                env={"DECOY_MASK_SECRET": _SECRET_A},
            )
        self._assert_refused_by_guard(result, tmp_path / "out.csv")

    def test_flag_ref_also_refused_when_keyprovider_absent(self, tmp_path: Path) -> None:
        """The probe fires for a --mask-secret flag ref, not just a YAML ref."""
        cfg = _mask_pipeline(tmp_path)
        with _simulate_pre_de02_engine():
            result = runner.invoke(
                app,
                ["run", str(cfg), "--mask-secret", "env:DECOY_MASK_SECRET"],
                env={"DECOY_MASK_SECRET": _SECRET_A},
            )
        self._assert_refused_by_guard(result, tmp_path / "out.csv")

    def test_probe_inert_without_secret_run_succeeds(self, tmp_path: Path) -> None:
        """The guard must not over-fire: with NO mask secret configured, the
        `if effective_ref:` gate is False, so the keyprovider probe is never
        attempted and a plain unkeyed run succeeds.

        This runs WITHOUT the pre-DE-02 block on purpose: the engine itself
        does a legitimate lazy `import decoy_engine.keyprovider` inside
        run_pipeline (execution/_pipeline.py), so blocking the module would
        break the run for a reason unrelated to the CLI guard. The point here
        is only that the guard leaves a no-secret run alone -- the guard is
        purely gated on a configured ref, which the refused tests above
        exercise. (Broader no-secret success coverage: TestMaskSecretKeyedOutput
        unkeyed runs, tests/e2e/test_run_command.py.)"""
        cfg = _mask_pipeline(tmp_path)  # no mask_secret_ref, no flag
        result = runner.invoke(app, ["run", str(cfg)], env={})
        assert result.exit_code == 0, (
            f"an unkeyed run must not be blocked by the mask-secret probe; "
            f"got {result.exit_code}. output={result.output!r}"
        )
        assert (tmp_path / "out.csv").exists()
