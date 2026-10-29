"""`decoy tokenize` + `decoy detokenize` over the engine's token-vault seam (B-1).

The tokenize verb runs a masking job whose `strategy: tokenize` columns are
replaced by deterministic surrogates, recording the (namespace, plaintext) ->
token mapping in a LOCAL SQLite vault; detokenize reverses it from that same
vault. Single-operator, local, no auth model (the multi-user de-tokenize auth
is the platform's B-6, not this CLI's).

Acceptance pinned here:
- tokenize masks the target column via the engine tokenize strategy, writes the
  mapping, and is deterministic (same plaintext + namespace -> same token).
- detokenize reverses it from the vault; a missing or wrong-namespace vault
  fails closed (no output).
- the same plaintext under two namespaces yields two distinct tokens.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_RUNTIME, EXIT_USAGE

runner = CliRunner()

# A throwaway >=32-byte mask secret (64 hex chars = 32 bytes), written to a file
# and referenced via `file:` so every tokenize run is keyed. tokenize REQUIRES a
# mask secret (B-1 BLOCKER): without one the tokens derive from the public job
# seed and are forgeable offline, so the fixture always supplies one.
_MASK_SECRET_HEX = "a" * 64


def _mask_secret_ref(tmp_path: Path) -> str:
    """Write the shared test mask secret and return its `file:` ref.

    Written at a fixed path per tmp_path so two `_pipeline` calls in one test
    share the SAME secret (determinism tests depend on that: a different secret
    would key different tokens)."""
    secret = tmp_path / "mask.secret"
    if not secret.exists():
        secret.write_text(_MASK_SECRET_HEX, encoding="utf-8")
    return f"file:{secret}"


def _pipeline(
    tmp_path: Path,
    columns: list[dict],
    *,
    emails: list[str] | None = None,
    out_name: str = "tokenized.csv",
    out_format: str = "csv",
    with_secret: bool = True,
) -> Path:
    emails = emails or ["a@x.com", "b@y.com", "a@x.com"]
    src = tmp_path / "in.csv"
    pd.DataFrame({"id": list(range(len(emails))), "email": emails}).to_csv(src, index=False)
    global_settings: dict = {"seed": 42}
    if with_secret:
        global_settings["mask_secret_ref"] = _mask_secret_ref(tmp_path)
    cfg = {
        "version": 2,
        "global_settings": global_settings,
        "sources": {"people": {"type": "file", "format": "csv", "path": str(src)}},
        "tables": [{"name": "people", "columns": columns}],
        "targets": {
            "people": {"type": "file", "format": out_format, "path": str(tmp_path / out_name)}
        },
    }
    p = tmp_path / "pipeline.yaml"
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return p


_TOKENIZE_COLS = [
    {"name": "id", "strategy": "passthrough"},
    {"name": "email", "strategy": "tokenize", "namespace": "people.email"},
]


class TestTokenizeRoundTrip:
    def test_tokenize_masks_column_and_writes_vault(self, tmp_path: Path) -> None:
        cfg = _pipeline(tmp_path, _TOKENIZE_COLS)
        vault = tmp_path / "tokens.db"
        result = runner.invoke(app, ["tokenize", str(cfg), "--vault", str(vault)])
        assert result.exit_code == 0, result.output
        assert vault.exists()
        out = pd.read_csv(tmp_path / "tokenized.csv", dtype=str)
        # The target column is replaced by tok_ surrogates, not the source value.
        assert all(v.startswith("tok_") for v in out["email"])
        assert "a@x.com" not in list(out["email"])
        # passthrough column is untouched.
        assert list(out["id"]) == ["0", "1", "2"]

    def test_repeated_value_gets_the_same_token(self, tmp_path: Path) -> None:
        cfg = _pipeline(tmp_path, _TOKENIZE_COLS)
        vault = tmp_path / "tokens.db"
        runner.invoke(app, ["tokenize", str(cfg), "--vault", str(vault)])
        out = pd.read_csv(tmp_path / "tokenized.csv", dtype=str)
        # rows 0 and 2 are both "a@x.com" -> the same token; row 1 differs.
        assert out["email"][0] == out["email"][2]
        assert out["email"][0] != out["email"][1]

    def test_detokenize_reverses_from_vault(self, tmp_path: Path) -> None:
        cfg = _pipeline(tmp_path, _TOKENIZE_COLS)
        vault = tmp_path / "tokens.db"
        runner.invoke(app, ["tokenize", str(cfg), "--vault", str(vault)])
        tokenized = tmp_path / "tokenized.csv"
        result = runner.invoke(
            app, ["detokenize", str(cfg), str(tokenized), "--vault", str(vault)]
        )
        assert result.exit_code == 0, result.output
        recovered = pd.read_csv(tmp_path / "tokenized.detokenized.csv", dtype=str)
        assert list(recovered["email"]) == ["a@x.com", "b@y.com", "a@x.com"]

    def test_detokenize_output_flag(self, tmp_path: Path) -> None:
        cfg = _pipeline(tmp_path, _TOKENIZE_COLS)
        vault = tmp_path / "tokens.db"
        runner.invoke(app, ["tokenize", str(cfg), "--vault", str(vault)])
        out = tmp_path / "recovered.csv"
        result = runner.invoke(
            app,
            [
                "detokenize",
                str(cfg),
                str(tmp_path / "tokenized.csv"),
                "--vault",
                str(vault),
                "-o",
                str(out),
            ],
        )
        assert result.exit_code == 0, result.output
        assert out.exists()

    def test_nulls_are_preserved_through_the_round_trip(self, tmp_path: Path) -> None:
        cfg = _pipeline(
            tmp_path, _TOKENIZE_COLS, emails=["a@x.com", "", "b@y.com"]
        )
        vault = tmp_path / "tokens.db"
        runner.invoke(app, ["tokenize", str(cfg), "--vault", str(vault)])
        out = pd.read_csv(tmp_path / "tokenized.csv", dtype=str)
        # the empty cell stays null (no token minted).
        assert pd.isna(out["email"][1])
        result = runner.invoke(
            app, ["detokenize", str(cfg), str(tmp_path / "tokenized.csv"), "--vault", str(vault)]
        )
        assert result.exit_code == 0, result.output
        recovered = pd.read_csv(tmp_path / "tokenized.detokenized.csv", dtype=str)
        assert list(recovered["email"][[0, 2]]) == ["a@x.com", "b@y.com"]
        assert pd.isna(recovered["email"][1])


class TestDeterminism:
    def test_same_plaintext_namespace_yields_same_token_across_runs(
        self, tmp_path: Path
    ) -> None:
        """Two independent tokenize runs (fresh vault each) over the same
        plaintext + namespace produce identical tokens -- the derivation is
        deterministic, and the vault makes it stable thereafter."""
        cfg1 = _pipeline(tmp_path, _TOKENIZE_COLS, out_name="t1.csv")
        v1 = tmp_path / "v1.db"
        runner.invoke(app, ["tokenize", str(cfg1), "--vault", str(v1)])
        cfg2 = _pipeline(tmp_path, _TOKENIZE_COLS, out_name="t2.csv")
        v2 = tmp_path / "v2.db"
        runner.invoke(app, ["tokenize", str(cfg2), "--vault", str(v2)])
        a = pd.read_csv(tmp_path / "t1.csv", dtype=str)["email"]
        b = pd.read_csv(tmp_path / "t2.csv", dtype=str)["email"]
        assert list(a) == list(b)

    def test_rerun_against_same_vault_reuses_tokens(self, tmp_path: Path) -> None:
        vault = tmp_path / "tokens.db"
        cfg1 = _pipeline(tmp_path, _TOKENIZE_COLS, out_name="run1.csv")
        first_run = runner.invoke(app, ["tokenize", str(cfg1), "--vault", str(vault)])
        assert first_run.exit_code == 0, first_run.output
        first = list(pd.read_csv(tmp_path / "run1.csv", dtype=str)["email"])
        # Re-run against the SAME vault but a FRESH output path: the second run
        # must reproduce the first run's tokens from the stored mapping, not just
        # reread the first run's output file. Both runs must succeed.
        cfg2 = _pipeline(tmp_path, _TOKENIZE_COLS, out_name="run2.csv")
        second_run = runner.invoke(app, ["tokenize", str(cfg2), "--vault", str(vault)])
        assert second_run.exit_code == 0, second_run.output
        second = list(pd.read_csv(tmp_path / "run2.csv", dtype=str)["email"])
        # Real surrogates (not passthrough plaintext), identical across runs.
        assert all(v.startswith("tok_") for v in second)
        assert first == second


class TestNamespaceDistinctness:
    def test_same_plaintext_two_namespaces_two_tokens(self, tmp_path: Path) -> None:
        """A value tokenized under two namespaces gets two distinct tokens, so
        the namespaces cannot be linked through a shared token."""
        cols = [
            {"name": "id", "strategy": "passthrough"},
            {"name": "email", "strategy": "tokenize", "namespace": "ns.one"},
            {"name": "email2", "strategy": "tokenize", "namespace": "ns.two"},
        ]
        # Build a source where email and email2 hold the SAME value per row.
        src = tmp_path / "in.csv"
        pd.DataFrame(
            {"id": [0, 1], "email": ["a@x.com", "b@y.com"], "email2": ["a@x.com", "b@y.com"]}
        ).to_csv(src, index=False)
        cfg = {
            "version": 2,
            "global_settings": {"seed": 42, "mask_secret_ref": _mask_secret_ref(tmp_path)},
            "sources": {"people": {"type": "file", "format": "csv", "path": str(src)}},
            "tables": [{"name": "people", "columns": cols}],
            "targets": {
                "people": {"type": "file", "format": "csv", "path": str(tmp_path / "out.csv")}
            },
        }
        p = tmp_path / "pipeline.yaml"
        p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
        vault = tmp_path / "tokens.db"
        result = runner.invoke(app, ["tokenize", str(p), "--vault", str(vault)])
        assert result.exit_code == 0, result.output
        out = pd.read_csv(tmp_path / "out.csv", dtype=str)
        # Same plaintext ("a@x.com") -> two different tokens across the two columns.
        assert out["email"][0] != out["email2"][0]
        assert out["email"][1] != out["email2"][1]


class TestFailClosed:
    def test_detokenize_missing_vault_fails_closed(self, tmp_path: Path) -> None:
        cfg = _pipeline(tmp_path, _TOKENIZE_COLS)
        vault = tmp_path / "tokens.db"
        runner.invoke(app, ["tokenize", str(cfg), "--vault", str(vault)])
        result = runner.invoke(
            app,
            [
                "detokenize",
                str(cfg),
                str(tmp_path / "tokenized.csv"),
                "--vault",
                str(tmp_path / "does_not_exist.db"),
            ],
        )
        assert result.exit_code == EXIT_USAGE
        assert "vault_not_found" in result.output
        assert not (tmp_path / "tokenized.detokenized.csv").exists()

    def test_detokenize_wrong_namespace_fails_closed(self, tmp_path: Path) -> None:
        cfg = _pipeline(tmp_path, _TOKENIZE_COLS)
        vault = tmp_path / "tokens.db"
        runner.invoke(app, ["tokenize", str(cfg), "--vault", str(vault)])
        # A config whose namespace does not match the one the vault was keyed on.
        wrong_cols = [
            {"name": "id", "strategy": "passthrough"},
            {"name": "email", "strategy": "tokenize", "namespace": "people.WRONG"},
        ]
        wrong = _pipeline(tmp_path, wrong_cols, out_name="unused.csv")
        result = runner.invoke(
            app,
            ["detokenize", str(wrong), str(tmp_path / "tokenized.csv"), "--vault", str(vault)],
        )
        assert result.exit_code == EXIT_USAGE
        assert "fail-closed" in result.output
        assert not (tmp_path / "tokenized.detokenized.csv").exists()

    def test_detokenize_against_non_vault_file_fails_closed(self, tmp_path: Path) -> None:
        cfg = _pipeline(tmp_path, _TOKENIZE_COLS)
        vault = tmp_path / "tokens.db"
        runner.invoke(app, ["tokenize", str(cfg), "--vault", str(vault)])
        junk = tmp_path / "junk.db"
        junk.write_bytes(b"not a sqlite db")
        result = runner.invoke(
            app, ["detokenize", str(cfg), str(tmp_path / "tokenized.csv"), "--vault", str(junk)]
        )
        assert result.exit_code == EXIT_USAGE
        assert "vault_not_a_token_vault" in result.output

    def test_tokenize_without_tokenize_column_fails_closed(self, tmp_path: Path) -> None:
        cols = [{"name": "id", "strategy": "passthrough"}, {"name": "email", "strategy": "redact"}]
        cfg = _pipeline(tmp_path, cols)
        result = runner.invoke(app, ["tokenize", str(cfg), "--vault", str(tmp_path / "t.db")])
        assert result.exit_code == EXIT_USAGE
        assert "no column declares" in result.output

    def test_tokenize_column_without_namespace_fails_closed(self, tmp_path: Path) -> None:
        cols = [
            {"name": "id", "strategy": "passthrough"},
            {"name": "email", "strategy": "tokenize"},  # no namespace
        ]
        cfg = _pipeline(tmp_path, cols)
        result = runner.invoke(app, ["tokenize", str(cfg), "--vault", str(tmp_path / "t.db")])
        assert result.exit_code == EXIT_USAGE
        assert "namespace" in result.output

    def test_tokenize_without_secret_fails_closed(self, tmp_path: Path) -> None:
        """B-1 BLOCKER: no mask secret (flag or YAML) is a coded refusal, not an
        unkeyed run -- a seed-keyed token is offline-forgeable (see
        TestSecretRequired), so tokenize must never produce one."""
        cfg = _pipeline(tmp_path, _TOKENIZE_COLS, with_secret=False)
        vault = tmp_path / "tokens.db"
        result = runner.invoke(app, ["tokenize", str(cfg), "--vault", str(vault)])
        assert result.exit_code == EXIT_USAGE
        assert "tokenize_requires_secret" in result.output
        # Fail closed: no vault, no output.
        assert not vault.exists()
        assert not (tmp_path / "tokenized.csv").exists()

    def test_mask_secret_flag_satisfies_the_requirement(self, tmp_path: Path) -> None:
        """A YAML with no mask_secret_ref is accepted when --mask-secret supplies
        the effective secret (the flag injects the same slot)."""
        cfg = _pipeline(tmp_path, _TOKENIZE_COLS, with_secret=False)
        vault = tmp_path / "tokens.db"
        ref = _mask_secret_ref(tmp_path)
        result = runner.invoke(
            app, ["tokenize", str(cfg), "--vault", str(vault), "--mask-secret", ref]
        )
        assert result.exit_code == 0, result.output
        assert vault.exists()

    def test_unresolvable_secret_gives_a_coded_error(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """LOW: a shape-valid --mask-secret that cannot resolve (here an unset env
        var) is a clean coded MaskSecretError at EXIT_USAGE, not the catch-all
        'unexpected MaskSecretError' at EXIT_RUNTIME. The message stays value-free
        (the engine names the env var, never the secret) and no empty vault is
        left behind."""
        monkeypatch.delenv("DECOY_TEST_UNSET_MASK_SECRET", raising=False)
        cfg = _pipeline(tmp_path, _TOKENIZE_COLS, with_secret=False)
        vault = tmp_path / "tokens.db"
        result = runner.invoke(
            app,
            ["tokenize", str(cfg), "--vault", str(vault),
             "--mask-secret", "env:DECOY_TEST_UNSET_MASK_SECRET"],
        )
        assert result.exit_code == EXIT_USAGE, result.output
        assert "missing_mask_secret" in result.output
        assert "unexpected" not in result.output  # not the catch-all
        assert not vault.exists()

    def test_weak_secret_gives_a_coded_error(self, tmp_path: Path) -> None:
        """LOW: a resolvable but <32-byte secret is a coded weak_mask_secret at
        EXIT_USAGE (value-free: a byte count, never the secret), not the
        catch-all. The reported length is the only secret-derived fact."""
        weak = tmp_path / "weak.secret"
        weak.write_text("deadbeef", encoding="utf-8")  # 4 bytes decoded, < 32
        cfg = _pipeline(tmp_path, _TOKENIZE_COLS, with_secret=False)
        vault = tmp_path / "tokens.db"
        result = runner.invoke(
            app,
            ["tokenize", str(cfg), "--vault", str(vault), "--mask-secret", f"file:{weak}"],
        )
        assert result.exit_code == EXIT_USAGE, result.output
        assert "weak_mask_secret" in result.output
        assert "unexpected" not in result.output

    def test_failed_run_leaves_no_empty_vault(self, tmp_path: Path) -> None:
        """LOW: the vault file is created before run_pipeline, so a run that fails
        after creation (here a tokenize column absent from the source) must not
        leave an empty vault on disk to be mistaken for output. The catch-all
        message no longer claims 'no output was written' it cannot guarantee."""
        cols = [
            {"name": "id", "strategy": "passthrough"},
            {"name": "ghost", "strategy": "tokenize", "namespace": "people.ghost"},
        ]
        cfg = _pipeline(tmp_path, cols)
        vault = tmp_path / "tokens.db"
        result = runner.invoke(app, ["tokenize", str(cfg), "--vault", str(vault)])
        assert result.exit_code == EXIT_RUNTIME, result.output
        assert not vault.exists()  # empty vault removed on failure
        # Normalize Rich's line wrapping before matching the message phrase.
        assert "aborted before the vault was committed" in " ".join(result.output.split())

    def test_failed_run_keeps_a_preexisting_vault(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """LOW: cleanup removes only a vault THIS run created. A second run that
        fails must leave an earlier run's real vault (and its mappings) intact, so
        the fix never deletes an operator's existing vault on a later failure."""
        monkeypatch.delenv("DECOY_TEST_UNSET_MASK_SECRET_2", raising=False)
        cfg_ok = _pipeline(tmp_path, _TOKENIZE_COLS)
        vault = tmp_path / "tokens.db"
        first = runner.invoke(app, ["tokenize", str(cfg_ok), "--vault", str(vault)])
        assert first.exit_code == 0, first.output
        assert vault.exists()

        # A second run against the SAME vault that fails at secret resolution
        # (unset env var) must not delete the pre-existing vault.
        cfg_fail = _pipeline(tmp_path, _TOKENIZE_COLS, with_secret=False, out_name="t2.csv")
        second = runner.invoke(
            app,
            ["tokenize", str(cfg_fail), "--vault", str(vault),
             "--mask-secret", "env:DECOY_TEST_UNSET_MASK_SECRET_2"],
        )
        assert second.exit_code == EXIT_USAGE, second.output
        assert vault.exists()  # pre-existing vault kept

        # The earlier run's mappings are intact: detokenize still reverses its
        # output from the vault the failed run left untouched.
        rev = runner.invoke(
            app,
            ["detokenize", str(cfg_ok), str(tmp_path / "tokenized.csv"), "--vault", str(vault)],
        )
        assert rev.exit_code == 0, rev.output
        recovered = pd.read_csv(tmp_path / "tokenized.detokenized.csv", dtype=str)
        assert "a@x.com" in list(recovered["email"])


class TestSecretRequired:
    def test_seed_only_forgery_no_longer_reproduces_the_token(self, tmp_path: Path) -> None:
        """The regression for the B-1 BLOCKER. An attacker holding only the
        tokenized output plus the config (public seed 42, no vault) recomputes the
        token the UNKEYED path would have produced:
        `tok_ + derive(job_seed, namespace, NFC(plaintext))[:32]`. With a real
        mask secret the token is keyed on the secret, not the public seed, so the
        offline recompute no longer matches -- re-identification needs the vault."""
        import unicodedata

        from decoy_engine.determinism import derive
        from decoy_engine.plan import job_seed_for_config

        cfg = _pipeline(tmp_path, _TOKENIZE_COLS, emails=["victim@example.com"])
        vault = tmp_path / "tokens.db"
        result = runner.invoke(app, ["tokenize", str(cfg), "--vault", str(vault)])
        assert result.exit_code == 0, result.output
        actual = pd.read_csv(tmp_path / "tokenized.csv", dtype=str)["email"][0]

        job_seed = job_seed_for_config({"global_settings": {"seed": 42}})
        forged = (
            "tok_"
            + derive(
                job_seed,
                "people.email",
                unicodedata.normalize("NFC", "victim@example.com").encode("utf-8"),
            ).hex()[:32]
        )
        assert actual.startswith("tok_")
        assert actual != forged, "keyed token must not equal the public-seed forgery"


class TestFormats:
    def test_parquet_target_round_trips(self, tmp_path: Path) -> None:
        """B-1 MEDIUM: tokenize writes the target in the config format (here
        Parquet, by path suffix); detokenize must read it back in that same
        format and reverse it, not fail on a hardcoded CSV read."""
        cfg = _pipeline(
            tmp_path, _TOKENIZE_COLS, out_name="tokenized.parquet", out_format="parquet"
        )
        vault = tmp_path / "tokens.db"
        result = runner.invoke(app, ["tokenize", str(cfg), "--vault", str(vault)])
        assert result.exit_code == 0, result.output
        out = pd.read_parquet(tmp_path / "tokenized.parquet")
        assert all(str(v).startswith("tok_") for v in out["email"])

        result = runner.invoke(
            app,
            ["detokenize", str(cfg), str(tmp_path / "tokenized.parquet"), "--vault", str(vault)],
        )
        assert result.exit_code == 0, result.output
        recovered = pd.read_parquet(tmp_path / "tokenized.detokenized.parquet")
        assert list(recovered["email"]) == ["a@x.com", "b@y.com", "a@x.com"]

    def test_detokenize_unreadable_target_fails_closed(self, tmp_path: Path) -> None:
        """A file that is not readable in its claimed format fails closed with a
        coded error (no raw codec exception, which could echo file bytes), and
        writes nothing."""
        cfg = _pipeline(tmp_path, _TOKENIZE_COLS)
        vault = tmp_path / "tokens.db"
        runner.invoke(app, ["tokenize", str(cfg), "--vault", str(vault)])
        bad = tmp_path / "corrupt.parquet"
        bad.write_bytes(b"not a parquet file")
        result = runner.invoke(
            app, ["detokenize", str(cfg), str(bad), "--vault", str(vault)]
        )
        assert result.exit_code == EXIT_USAGE
        assert "detokenize_unreadable_target" in result.output
        assert not (tmp_path / "corrupt.detokenized.parquet").exists()


class TestJsonAndSafety:
    def test_tokenize_json_envelope(self, tmp_path: Path) -> None:
        cfg = _pipeline(tmp_path, _TOKENIZE_COLS)
        vault = tmp_path / "tokens.db"
        result = runner.invoke(app, ["tokenize", str(cfg), "--vault", str(vault), "--json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert payload["command"] == "tokenize"
        assert payload["status"] == "ok"
        assert payload["rows"] == 3
        assert payload["vault_entries"] == 2
        assert payload["columns"] == [
            {"table": "people", "column": "email", "namespace": "people.email"}
        ]

    def test_no_plaintext_in_tokenize_output(self, tmp_path: Path) -> None:
        """The tokenize surface never prints a source value (keep plaintext out
        of stdout/logs)."""
        cfg = _pipeline(tmp_path, _TOKENIZE_COLS)
        vault = tmp_path / "tokens.db"
        result = runner.invoke(app, ["tokenize", str(cfg), "--vault", str(vault)])
        assert result.exit_code == 0, result.output
        assert "a@x.com" not in result.output
        assert "b@y.com" not in result.output

    def test_detokenize_json_envelope(self, tmp_path: Path) -> None:
        cfg = _pipeline(tmp_path, _TOKENIZE_COLS)
        vault = tmp_path / "tokens.db"
        runner.invoke(app, ["tokenize", str(cfg), "--vault", str(vault)])
        result = runner.invoke(
            app,
            ["detokenize", str(cfg), str(tmp_path / "tokenized.csv"), "--vault", str(vault), "--json"],
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert payload["command"] == "detokenize"
        assert payload["status"] == "ok"
        assert payload["table"] == "people"


class TestHelp:
    def test_tokenize_help_lists_see_also(self) -> None:
        result = runner.invoke(app, ["tokenize", "--help"])
        assert result.exit_code == 0
        assert "detokenize" in result.output

    def test_detokenize_help_lists_see_also(self) -> None:
        result = runner.invoke(app, ["detokenize", "--help"])
        assert result.exit_code == 0
        assert "tokenize" in result.output


_RAW_SECRET = "RAWSECRETSENTINEL" + "z" * 20


def _tokenize_two_columns(tmp_path: Path) -> tuple[Path, Path]:
    """Config with two tokenize columns and its tokenized output + vault."""
    cols = [
        {"name": "id", "strategy": "passthrough"},
        {"name": "email", "strategy": "tokenize", "namespace": "ns.one"},
        {"name": "email2", "strategy": "tokenize", "namespace": "ns.two"},
    ]
    src = tmp_path / "in.csv"
    pd.DataFrame(
        {"id": [0, 1], "email": ["a@x.com", "b@y.com"], "email2": ["a@x.com", "b@y.com"]}
    ).to_csv(src, index=False)
    cfg = {
        "version": 2,
        "global_settings": {"seed": 42, "mask_secret_ref": _mask_secret_ref(tmp_path)},
        "sources": {"people": {"type": "file", "format": "csv", "path": str(src)}},
        "tables": [{"name": "people", "columns": cols}],
        "targets": {
            "people": {"type": "file", "format": "csv", "path": str(tmp_path / "tokenized.csv")}
        },
    }
    p = tmp_path / "pipeline.yaml"
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    vault = tmp_path / "tokens.db"
    res = runner.invoke(app, ["tokenize", str(p), "--vault", str(vault)])
    assert res.exit_code == 0, res.output
    return p, vault


class TestOutputNotClobbered:
    def test_existing_default_output_is_refused(self, tmp_path: Path) -> None:
        cfg = _pipeline(tmp_path, _TOKENIZE_COLS)
        vault = tmp_path / "tokens.db"
        runner.invoke(app, ["tokenize", str(cfg), "--vault", str(vault)])
        existing = tmp_path / "tokenized.detokenized.csv"
        existing.write_bytes(b"precious")
        result = runner.invoke(
            app, ["detokenize", str(cfg), str(tmp_path / "tokenized.csv"), "--vault", str(vault)]
        )
        assert result.exit_code == EXIT_USAGE, result.output
        assert "detokenize_output_exists" in result.output
        assert existing.read_bytes() == b"precious"

    def test_same_stem_different_extension_does_not_clobber(self, tmp_path: Path) -> None:
        cfg = _pipeline(tmp_path, _TOKENIZE_COLS)
        vault = tmp_path / "tokens.db"
        runner.invoke(app, ["tokenize", str(cfg), "--vault", str(vault)])
        csv_in = tmp_path / "tokenized.csv"
        # Reader treats every non-Parquet extension as CSV; give the .tsv a
        # different (valid) body so a clobber would change the first output.
        tsv_in = tmp_path / "tokenized.tsv"
        tsv_in.write_text("\n".join(csv_in.read_text().splitlines()[:2]) + "\n")
        first = runner.invoke(
            app, ["detokenize", str(cfg), str(csv_in), "--vault", str(vault)]
        )
        assert first.exit_code == 0, first.output
        out = tmp_path / "tokenized.detokenized.csv"
        before = out.read_bytes()
        second = runner.invoke(
            app, ["detokenize", str(cfg), str(tsv_in), "--vault", str(vault)]
        )
        assert second.exit_code == EXIT_USAGE, second.output
        assert "detokenize_output_exists" in second.output
        assert out.read_bytes() == before

    def test_explicit_output_may_overwrite(self, tmp_path: Path) -> None:
        cfg = _pipeline(tmp_path, _TOKENIZE_COLS)
        vault = tmp_path / "tokens.db"
        runner.invoke(app, ["tokenize", str(cfg), "--vault", str(vault)])
        out = tmp_path / "chosen.csv"
        out.write_text("old")
        result = runner.invoke(
            app,
            ["detokenize", str(cfg), str(tmp_path / "tokenized.csv"),
             "--vault", str(vault), "-o", str(out)],
        )
        assert result.exit_code == 0, result.output
        assert "a@x.com" in out.read_text()


class TestRequireAllColumns:
    def test_missing_declared_column_fails_closed(self, tmp_path: Path) -> None:
        cfg, vault = _tokenize_two_columns(tmp_path)
        tokenized = tmp_path / "tokenized.csv"
        # email resolves from a valid vault; only email2 is absent.
        pd.read_csv(tokenized, dtype=str).drop(columns=["email2"]).to_csv(
            tmp_path / "partial.csv", index=False
        )
        result = runner.invoke(
            app, ["detokenize", str(cfg), str(tmp_path / "partial.csv"), "--vault", str(vault)]
        )
        assert result.exit_code == EXIT_USAGE, result.output
        assert "detokenize_column_missing" in result.output
        assert "email2" in result.output
        assert not (tmp_path / "partial.detokenized.csv").exists()


class TestNoLeakOnErrorPaths:
    """Sentinels (plaintexts, tokens, the mask secret, a raw secret ref) must not
    surface in ANY error path of either verb, human or JSON."""

    def _sentinels(self, tmp_path: Path) -> list[str]:
        toks = pd.read_csv(tmp_path / "tokenized.csv", dtype=str)
        return ["a@x.com", "b@y.com", _MASK_SECRET_HEX, *toks["email"], *toks["email2"]]

    @staticmethod
    def _assert_clean(result, sentinels: list[str]) -> None:
        text = result.output + (result.stderr if result.stderr_bytes else "")
        for s in sentinels:
            assert s not in text, "leaked a sentinel value"

    def test_detokenize_error_paths(self, tmp_path: Path) -> None:
        cfg, vault = _tokenize_two_columns(tmp_path)
        sentinels = self._sentinels(tmp_path)
        tokenized = tmp_path / "tokenized.csv"

        junk = tmp_path / "junk.db"
        junk.write_bytes(b"not a sqlite db")
        stale = tmp_path / "stale.db"
        stale.write_bytes(vault.read_bytes())
        conn = sqlite3.connect(str(stale))
        conn.execute("UPDATE meta SET value='999' WHERE key='schema_version'")
        conn.commit()
        conn.close()
        partial = tmp_path / "partial.csv"
        pd.read_csv(tokenized, dtype=str).drop(columns=["email2"]).to_csv(partial, index=False)
        wrong_ns = yaml.safe_load(cfg.read_text())
        wrong_ns["tables"][0]["columns"][1]["namespace"] = "ns.WRONG"
        wrong_cfg = tmp_path / "wrong.yaml"
        wrong_cfg.write_text(yaml.safe_dump(wrong_ns))
        # Schema-invalid configs that carry a raw secret in the value: the
        # pydantic ValidationError path must not echo it.
        bad_cfgs = []
        for i, gs in enumerate(
            ({"mask_secret_ref": [_RAW_SECRET]}, {"mask_secret": _RAW_SECRET})
        ):
            raw = yaml.safe_load(cfg.read_text())
            raw["global_settings"].pop("mask_secret_ref")
            raw["global_settings"].update(gs)
            bad = tmp_path / f"bad{i}.yaml"
            bad.write_text(yaml.safe_dump(raw))
            bad_cfgs.append(bad)
        (tmp_path / "tokenized.detokenized.csv").write_text("x")

        cases = [
            [str(cfg), str(tokenized), "--vault", str(vault)],  # output exists
            [str(cfg), str(partial), "--vault", str(vault)],  # missing column
            [str(cfg), str(tokenized), "--vault", str(stale), "-o", str(tmp_path / "o1.csv")],
            [str(cfg), str(tokenized), "--vault", str(junk), "-o", str(tmp_path / "o2.csv")],
            [str(wrong_cfg), str(tokenized), "--vault", str(vault), "-o", str(tmp_path / "o3.csv")],
            *(
                [str(b), str(tokenized), "--vault", str(vault), "-o", str(tmp_path / f"b{b.stem}.csv")]
                for b in bad_cfgs
            ),
        ]
        for args in cases:
            for extra in ([], ["--json"]):
                result = runner.invoke(app, ["detokenize", *args, *extra])
                assert result.exit_code != 0, result.output
                self._assert_clean(result, [*sentinels, _RAW_SECRET])

    def test_tokenize_error_paths(self, tmp_path: Path) -> None:
        cfg, _vault = _tokenize_two_columns(tmp_path)
        sentinels = self._sentinels(tmp_path)
        bad_ref = yaml.safe_load(cfg.read_text())
        bad_ref["global_settings"]["mask_secret_ref"] = f"literal:{_RAW_SECRET}"
        bad_ref_cfg = tmp_path / "badref.yaml"
        bad_ref_cfg.write_text(yaml.safe_dump(bad_ref))
        weak = tmp_path / "weak.secret"
        weak.write_text("short")
        for args in (
            [str(bad_ref_cfg), "--vault", str(tmp_path / "v1.db")],
            [str(cfg), "--vault", str(tmp_path / "v2.db"), "--mask-secret", f"file:{weak}"],
            [str(cfg), "--vault", str(tmp_path / "v3.db"), "--mask-secret", f"literal:{_RAW_SECRET}"],
        ):
            for extra in ([], ["--json"]):
                result = runner.invoke(app, ["tokenize", *args, *extra])
                assert result.exit_code != 0, result.output
                self._assert_clean(result, [*sentinels, _RAW_SECRET])
