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
from pathlib import Path

import pandas as pd
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_USAGE

runner = CliRunner()


def _pipeline(
    tmp_path: Path,
    columns: list[dict],
    *,
    emails: list[str] | None = None,
    out_name: str = "tokenized.csv",
) -> Path:
    emails = emails or ["a@x.com", "b@y.com", "a@x.com"]
    src = tmp_path / "in.csv"
    pd.DataFrame({"id": list(range(len(emails))), "email": emails}).to_csv(src, index=False)
    cfg = {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {"people": {"type": "file", "format": "csv", "path": str(src)}},
        "tables": [{"name": "people", "columns": columns}],
        "targets": {
            "people": {"type": "file", "format": "csv", "path": str(tmp_path / out_name)}
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
        cfg = _pipeline(tmp_path, _TOKENIZE_COLS)
        vault = tmp_path / "tokens.db"
        runner.invoke(app, ["tokenize", str(cfg), "--vault", str(vault)])
        first = list(pd.read_csv(tmp_path / "tokenized.csv", dtype=str)["email"])
        # Re-run against the SAME vault: stored tokens are reused, output stable.
        runner.invoke(app, ["tokenize", str(cfg), "--vault", str(vault)])
        second = list(pd.read_csv(tmp_path / "tokenized.csv", dtype=str)["email"])
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
            "version": 1,
            "global_settings": {"seed": 42},
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
