"""The local token vault mints the engine's per-vault derivation scope once, at creation."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from decoy.cli._token_vault import LocalTokenVault


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
