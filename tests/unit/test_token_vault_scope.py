"""The local token vault mints the engine's per-vault derivation scope once, at creation."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from decoy.cli._token_vault import _SCOPE_KEY, LocalTokenVault


def test_a_new_vault_has_a_scope_the_engine_accepts(tmp_path: Path) -> None:
    vault = LocalTokenVault(tmp_path / "v.db", create=True)
    scope = vault.derivation_scope
    vault.close()
    assert isinstance(scope, bytes) and 16 <= len(scope) <= 64


def test_the_scope_is_kept_across_reopen(tmp_path: Path) -> None:
    path = tmp_path / "v.db"
    first = LocalTokenVault(path, create=True)
    scope = first.derivation_scope
    first.close()
    again = LocalTokenVault(path, create=True)
    assert again.derivation_scope == scope
    again.close()


def test_two_vaults_get_different_scopes(tmp_path: Path) -> None:
    a = LocalTokenVault(tmp_path / "a.db", create=True)
    b = LocalTokenVault(tmp_path / "b.db", create=True)
    assert a.derivation_scope != b.derivation_scope
    a.close()
    b.close()


def test_a_vault_written_without_a_scope_never_gets_one(tmp_path: Path) -> None:
    """A vault from before scoped derivation holds tokens minted under the old derivation."""
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE token_map (namespace TEXT NOT NULL, plaintext TEXT NOT NULL,"
        " token TEXT NOT NULL, PRIMARY KEY (namespace, plaintext));"
        "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);"
        "INSERT INTO meta VALUES ('schema_version', '1');"
    )
    conn.commit()
    conn.close()
    vault = LocalTokenVault(path, create=True)
    assert vault.derivation_scope is None
    vault.close()


def test_a_second_opener_that_lost_the_scope_race_shares_the_winners_scope(
    tmp_path: Path,
) -> None:
    """Both openers saw an empty meta table; the winner's scope row committed first."""
    path = tmp_path / "v.db"
    winner_scope = b"\x05" * 32
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE token_map (namespace TEXT NOT NULL, plaintext TEXT NOT NULL,"
        " token TEXT NOT NULL, PRIMARY KEY (namespace, plaintext));"
        "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);"
    )
    conn.execute("INSERT INTO meta VALUES (?, ?)", (_SCOPE_KEY, winner_scope.hex()))
    conn.commit()
    conn.close()
    loser = LocalTokenVault(path, create=True)
    assert loser.derivation_scope == winner_scope
    loser.close()


def test_only_the_opener_that_created_the_file_reports_created(tmp_path: Path) -> None:
    path = tmp_path / "v.db"
    first = LocalTokenVault(path, create=True)
    assert first.created is True
    first.close()
    second = LocalTokenVault(path, create=True)
    assert second.created is False
    second.close()


def test_a_second_writer_is_refused_while_the_first_holds_the_vault(tmp_path: Path) -> None:
    from decoy.cli._token_vault import TokenVaultError

    path = tmp_path / "v.db"
    first = LocalTokenVault(path, create=True)
    try:
        with pytest.raises(TokenVaultError) as raised:
            LocalTokenVault(path, create=True)
        assert raised.value.code == "vault_busy"
        assert str(path) not in raised.value.message
    finally:
        first.close()
    again = LocalTokenVault(path, create=True)
    again.close()
