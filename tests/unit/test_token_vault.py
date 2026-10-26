"""`decoy.cli._token_vault.LocalTokenVault` -- the local SQLite token store (B-1).

The store implements the engine's `TokenVaultWriter` protocol
(`lookup_existing` / `put`) for the tokenize path plus a `reverse` lookup for
detokenize. These tests pin its namespace scoping, idempotent/conflict write
behavior, the commit-on-success durability contract, and the fail-closed opens
detokenize relies on.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from decoy.cli._token_vault import (
    LocalTokenVault,
    TokenVaultError,
    iter_tokenize_columns,
)


def test_put_lookup_and_reverse_roundtrip(tmp_path: Path) -> None:
    vp = tmp_path / "t.db"
    with LocalTokenVault(vp, create=True) as v:
        assert v.lookup_existing("ns", "a") is None
        v.put("ns", "a", "tok_1")
        v.put("ns", "b", "tok_2")
        v.commit()
        assert v.lookup_existing("ns", "a") == "tok_1"
        assert v.reverse("ns", "tok_1") == "a"
        assert v.reverse("ns", "tok_missing") is None
        assert v.count() == 2


def test_namespace_scopes_both_directions(tmp_path: Path) -> None:
    """The same plaintext under two namespaces is two rows with two tokens;
    a reverse lookup never crosses namespaces."""
    vp = tmp_path / "t.db"
    with LocalTokenVault(vp, create=True) as v:
        v.put("ns1", "a", "tok_one")
        v.put("ns2", "a", "tok_two")
        v.commit()
        assert v.lookup_existing("ns1", "a") == "tok_one"
        assert v.lookup_existing("ns2", "a") == "tok_two"
        # reverse is scoped: ns1's token does not resolve under ns2.
        assert v.reverse("ns1", "tok_one") == "a"
        assert v.reverse("ns2", "tok_one") is None


def test_put_is_idempotent_on_same_token(tmp_path: Path) -> None:
    vp = tmp_path / "t.db"
    with LocalTokenVault(vp, create=True) as v:
        v.put("ns", "a", "tok_1")
        v.put("ns", "a", "tok_1")  # no raise, no duplicate
        v.commit()
        assert v.count() == 1


def test_put_conflict_on_different_token_fails_closed(tmp_path: Path) -> None:
    vp = tmp_path / "t.db"
    with LocalTokenVault(vp, create=True) as v:
        v.put("ns", "distinctive_plaintext", "tok_original")
        with pytest.raises(TokenVaultError) as exc:
            v.put("ns", "distinctive_plaintext", "tok_DIFFERENT")
    assert exc.value.code == "vault_token_conflict"
    # The value-free message never names the plaintext or either token.
    assert "distinctive_plaintext" not in exc.value.message
    assert "tok_original" not in exc.value.message
    assert "tok_DIFFERENT" not in exc.value.message


def test_uncommitted_writes_are_discarded_on_close(tmp_path: Path) -> None:
    """A run that fails before commit() leaves no partial mapping behind."""
    vp = tmp_path / "t.db"
    v = LocalTokenVault(vp, create=True)
    v.put("ns", "a", "tok_1")  # never committed
    v.close()
    with LocalTokenVault(vp, create=False) as v2:
        assert v2.count() == 0
        assert v2.reverse("ns", "tok_1") is None


def test_open_missing_vault_without_create_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(TokenVaultError) as exc:
        LocalTokenVault(tmp_path / "nope.db", create=False)
    assert exc.value.code == "vault_not_found"


def test_open_non_sqlite_file_fails_closed(tmp_path: Path) -> None:
    junk = tmp_path / "junk.db"
    junk.write_bytes(b"this is not a sqlite database")
    with pytest.raises(TokenVaultError) as exc:
        LocalTokenVault(junk, create=False)
    assert exc.value.code == "vault_not_a_token_vault"


def test_open_sqlite_without_token_map_fails_closed(tmp_path: Path) -> None:
    import sqlite3

    other = tmp_path / "other.db"
    conn = sqlite3.connect(str(other))
    conn.execute("CREATE TABLE unrelated (x INTEGER)")
    conn.commit()
    conn.close()
    with pytest.raises(TokenVaultError) as exc:
        LocalTokenVault(other, create=False)
    assert exc.value.code == "vault_not_a_token_vault"


def test_create_makes_parent_dirs(tmp_path: Path) -> None:
    vp = tmp_path / "nested" / "dir" / "t.db"
    with LocalTokenVault(vp, create=True) as v:
        v.put("ns", "a", "tok_1")
        v.commit()
    assert vp.exists()


def test_iter_tokenize_columns_reads_strategy_and_namespace() -> None:
    cfg = {
        "tables": [
            {
                "name": "people",
                "columns": [
                    {"name": "id", "strategy": "passthrough"},
                    {"name": "email", "strategy": "tokenize", "namespace": "people.email"},
                    {"name": "ssn", "strategy": "tokenize", "namespace": "people.ssn"},
                ],
            },
            {"name": "other", "columns": [{"name": "x", "strategy": "redact"}]},
        ]
    }
    assert list(iter_tokenize_columns(cfg, "people")) == [
        ("email", "people.email"),
        ("ssn", "people.ssn"),
    ]
    assert list(iter_tokenize_columns(cfg, "other")) == []


def test_iter_tokenize_columns_yields_empty_namespace_when_missing() -> None:
    cfg = {"tables": [{"name": "t", "columns": [{"name": "c", "strategy": "tokenize"}]}]}
    assert list(iter_tokenize_columns(cfg, "t")) == [("c", "")]
