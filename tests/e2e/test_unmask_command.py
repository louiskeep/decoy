"""End-to-end tests for `decoy unmask` (capability-gaps WS1, 2026-06-12).

The detokenization verb: `decoy run` masks, `decoy unmask` recovers the
fpe columns from the masked file using the SAME config (which carries
the seed -- the secret -- plus namespace/charset per column). Hash and
other one-way columns stay as-is and are reported irreversible.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_USAGE

runner = CliRunner()


def _flatten(output: str) -> str:
    """Collapse all whitespace (incl. Rich line-wraps) to single spaces, so
    substring/regex matches on the summary don't depend on terminal width."""
    return " ".join(output.split())


# One regex per surfaced bucket. Each label is distinctive enough that it
# never collides with a note's detail text, so parsing the flattened output
# recovers the exact number the summary DISPLAYED for that bucket.
_BUCKET_PATTERNS = {
    "reversed": r"(\d+) column\(s\) reversed",
    "reversed_unverified": r"(\d+) reversed \(unverified\)",
    "vault_reversed": r"(\d+) vault-reversed",
    "vault_miss": r"(\d+) vault-miss",
    "irreversible": r"(\d+) irreversible",
    "untouched": r"(\d+) untouched",
    "table_missing": r"(\d+) configured table\(s\) not in this input",
}

# The six statuses a PRESENT column can carry, enumerated from
# decoy_engine/unmask.py (reversed | reversed_unverified | vault_reversed |
# vault_miss | irreversible | untouched). `table_missing` is deliberately
# excluded: it is a pseudo-entry for an absent configured table, not a column.
_COLUMN_BUCKETS = (
    "reversed",
    "reversed_unverified",
    "vault_reversed",
    "vault_miss",
    "irreversible",
    "untouched",
)


def _displayed_counts(output: str) -> dict[str, int]:
    """Parse the numbers the console summary actually showed, defaulting an
    un-surfaced bucket to 0 (its clause is omitted only when the count is 0)."""
    flat = _flatten(output)
    counts: dict[str, int] = {}
    for name, pattern in _BUCKET_PATTERNS.items():
        m = re.search(pattern, flat)
        counts[name] = int(m.group(1)) if m else 0
    return counts


def _assert_census_complete(config: Path, masked: Path, out: Path, *args: str) -> str:
    """Drive `decoy unmask` twice (JSON for ground truth, plain for display)
    and assert the summary is a COMPLETE census: every real column entry
    falls into exactly one surfaced bucket, and absent tables are reported
    apart from columns. Returns the plain output for further assertions.

    This is the class-level invariant -- it fails if ANY status silently
    vanishes from the arithmetic, not just the one that prompted the fix.
    """
    json_res = runner.invoke(
        app, ["unmask", str(config), str(masked), "-o", str(out), *args, "--json"]
    )
    assert json_res.exit_code == 0, json_res.output
    entries = json.loads(json_res.output)["columns"]
    real = [e for e in entries if e["status"] != "table_missing"]
    missing = [e for e in entries if e["status"] == "table_missing"]

    plain_res = runner.invoke(
        app, ["unmask", str(config), str(masked), "-o", str(out), *args]
    )
    assert plain_res.exit_code == 0, plain_res.output
    counts = _displayed_counts(plain_res.output)

    displayed_columns = sum(counts[b] for b in _COLUMN_BUCKETS)
    assert displayed_columns == len(real), (
        f"census incomplete: summary accounts for {displayed_columns} column(s) "
        f"but the engine returned {len(real)} real column entr(ies). "
        f"counts={counts} statuses={[e['status'] for e in real]}"
    )
    assert counts["table_missing"] == len(missing), (
        f"table_missing miscount: displayed {counts['table_missing']}, "
        f"engine returned {len(missing)}"
    )
    return plain_res.output


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


@pytest.fixture
def csv_with_pan(tmp_path: Path) -> Path:
    """Luhn-valid PAN column -- `decoy init` scaffolds it to `strategy: fpe`
    (`_INFERENCE_TABLE` -> pan detector), matching the shape of
    `csv_with_date_zip_pan_id` in test_init_command.py."""
    csv = tmp_path / "accounts.csv"
    pd.DataFrame(
        {
            "card_number": [
                "4111111111111111",
                "4012888888881881",
                "5500005555555559",
                "4000000000000002",
            ],
        }
    ).to_csv(csv, index=False)
    return csv


class TestUnmaskConsoleSurfacesReversedUnverified:
    """Real-world reproduction: `decoy init` scaffolds an fpe column for a
    PAN, `decoy run` with no mask secret masks it under the non-secret
    job_seed fallback, and `decoy unmask` decrypts it back with status
    `reversed_unverified`. Before the fix, the console summary counted only
    `reversed`/`irreversible`/`untouched` and printed a `note:` only for
    `("reversed", "vault_reversed", "vault_miss")` -- so a `reversed_
    unverified` column was invisible: not counted (summary said "0 column(s)
    reversed" despite a PAN having been decrypted) and its "may be WRONG
    plaintext" authentication caveat was never printed. Only `--json`
    surfaced it correctly.
    """

    def test_console_summary_reports_reversed_unverified_and_warning(
        self, csv_with_pan: Path, tmp_path: Path
    ) -> None:
        out_cfg = tmp_path / "pipeline.yaml"
        init_result = runner.invoke(
            app, ["init", str(csv_with_pan), "--out", str(out_cfg), "--quiet"]
        )
        assert init_result.exit_code == 0, init_result.output

        run_result = runner.invoke(app, ["run", str(out_cfg)])
        assert run_result.exit_code == 0, run_result.output

        masked = tmp_path / "accounts.masked.csv"
        assert masked.exists(), "decoy run did not write the scaffolded output path"

        out = tmp_path / "recovered.csv"
        unmask_result = runner.invoke(
            app,
            ["unmask", str(out_cfg), str(masked), "--output", str(out)],
        )
        assert unmask_result.exit_code == 0, unmask_result.output
        # Rich wraps the summary across physical lines under a narrow width
        # (the CliRunner default is 80), so collapse ALL whitespace before
        # matching -- a substring check on a single physical line would give a
        # false pass/fail purely from the terminal width.
        flat = _flatten(unmask_result.output)

        # Pin the EXACT contract, not just "some 4th term exists": ordinary
        # `reversed` MUST stay 0 (this fpe reversal is NOT authenticated), and
        # the unverified reversal MUST be its own count of 1. A future impl
        # that wrongly folds unverified into `reversed` fails both halves.
        assert "0 column(s) reversed" in flat, flat
        assert "1 reversed (unverified)" in flat, flat
        # The authentication caveat must reach the console, not just --json.
        assert "wrong plaintext" in flat.lower() or "unauthenticated" in flat.lower(), (
            f"missing authentication warning note: {flat!r}"
        )


def _multitable_cfg(tmp_path: Path) -> tuple[Path, Path]:
    """A two-table mask config where only `accounts` is present in the input.
    `accounts.card` is fpe (reverses under the job_seed fallback ->
    reversed_unverified); `orders` is configured but never masked to a file,
    so unmasking the accounts file alone yields a `table_missing` pseudo-entry
    for orders. Returns (config_path, masked_accounts_path)."""
    src = tmp_path / "acc.csv"
    pd.DataFrame(
        {"card": ["4111111111111111", "4012888888881881", "5500005555555559"]}
    ).to_csv(src, index=False)
    masked = tmp_path / "acc.masked.csv"
    cfg = {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {"accounts": {"type": "file", "format": "csv", "path": str(src)}},
        "tables": [
            {
                "name": "accounts",
                "columns": [
                    {
                        "name": "card",
                        "strategy": "fpe",
                        "namespace": "pan_ns",
                        "provider_config": {"charset": "digits"},
                    }
                ],
            },
            {
                "name": "orders",
                "columns": [
                    {
                        "name": "order_id",
                        "strategy": "fpe",
                        "namespace": "ord_ns",
                        "provider_config": {"charset": "digits"},
                    }
                ],
            },
        ],
        "targets": {
            "accounts": {"type": "file", "format": "csv", "path": str(masked)}
        },
    }
    cfg_path = tmp_path / "pipeline.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    result = runner.invoke(app, ["run", str(cfg_path)])
    assert result.exit_code == 0, result.output
    assert masked.exists()
    return cfg_path, masked


class TestUnmaskSummaryIsCompleteCensus:
    """Class-level guard (dennis + Codex two-model gate): the human summary
    must be a COMPLETE census -- every real column entry lands in exactly one
    surfaced bucket, and absent tables are reported apart from columns. The
    original fix closed only `reversed_unverified`; `vault_miss` and
    `table_missing` were still un-surfaced, so the arithmetic still lied.
    """

    def test_census_invariant_holds_with_reversed_unverified_and_table_missing(
        self, tmp_path: Path
    ) -> None:
        cfg_path, masked = _multitable_cfg(tmp_path)
        out = tmp_path / "recovered.csv"
        plain = _assert_census_complete(
            cfg_path, masked, out, "--table", "accounts"
        )
        flat = _flatten(plain)
        # The absent table is surfaced as its OWN clause, never counted as a
        # column, and its note names the table (not the "*" placeholder).
        assert "0 column(s) reversed" in flat, flat
        assert "1 reversed (unverified)" in flat, flat
        assert "1 configured table(s) not in this input" in flat, flat
        assert "note: orders:" in flat, flat

    def test_vault_miss_is_counted_and_census_holds(self, tmp_path: Path) -> None:
        # vault_miss arises when a vault is present but reverses NO value of a
        # requested column. Build two vaults under the SAME seed from DIFFERENT
        # data, then unmask dataset-1's output with dataset-2's vault: the seed
        # matches (so no key-mismatch error) but no masked value is a key in it.
        def _cfg(src: Path, out: Path) -> dict:
            return {
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
                            }
                        ],
                    }
                ],
                "targets": {
                    "accounts": {"type": "file", "format": "csv", "path": str(out)}
                },
            }

        src1 = tmp_path / "in1.csv"
        pd.DataFrame({"email": [f"user{i}@x.com" for i in range(10)]}).to_csv(
            src1, index=False
        )
        out1 = tmp_path / "out1.csv"
        cfg1 = tmp_path / "cfg1.yaml"
        cfg1.write_text(yaml.safe_dump(_cfg(src1, out1)), encoding="utf-8")
        vault_a = tmp_path / "vaultA.bin"
        assert (
            runner.invoke(app, ["run", str(cfg1), "--vault", str(vault_a)]).exit_code
            == 0
        )

        src2 = tmp_path / "in2.csv"
        pd.DataFrame({"email": [f"alt{i}@x.com" for i in range(10)]}).to_csv(
            src2, index=False
        )
        out2 = tmp_path / "out2.csv"
        cfg2 = tmp_path / "cfg2.yaml"
        cfg2.write_text(yaml.safe_dump(_cfg(src2, out2)), encoding="utf-8")
        vault_b = tmp_path / "vaultB.bin"
        assert (
            runner.invoke(app, ["run", str(cfg2), "--vault", str(vault_b)]).exit_code
            == 0
        )

        out = tmp_path / "recovered.csv"
        plain = _assert_census_complete(
            cfg1, out1, out, "--vault", str(vault_b)
        )
        flat = _flatten(plain)
        # The vault_miss column is counted (not dropped to nowhere) and noted.
        assert "1 vault-miss" in flat, flat
        assert "0 column(s) reversed" in flat, flat
        assert "note: email:" in flat, flat
