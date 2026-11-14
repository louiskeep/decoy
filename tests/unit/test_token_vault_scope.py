"""The local token vault mints the engine's per-vault derivation scope once, at creation."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from decoy._private_file import advisory_lock_available
from decoy.cli._token_vault import _SCOPE_KEY, LocalTokenVault

posix_only = pytest.mark.skipif(not advisory_lock_available(), reason="needs an advisory lock")


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


@posix_only
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


@posix_only
def test_the_file_is_created_only_after_the_writer_lock_is_held(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fcntl
    import os

    from decoy.cli import _token_vault

    path = tmp_path / "v.db"
    real = _token_vault.create_private_exclusive
    seen: list[bool] = []

    def _spy(target: Path) -> bool:
        probe = os.open(target.with_name(f".{target.name}.lock"), os.O_RDWR)
        try:
            try:
                fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
                seen.append(False)  # the lock was free, so this run did not hold it
            except OSError:
                seen.append(True)
        finally:
            os.close(probe)
        return real(target)

    monkeypatch.setattr(_token_vault, "create_private_exclusive", _spy)
    LocalTokenVault(path, create=True).close()
    assert seen == [True]


def test_without_an_advisory_lock_a_failed_run_never_deletes_its_vault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from decoy.cli import _token_vault

    monkeypatch.setattr(_token_vault, "advisory_lock_available", lambda: False)
    path = tmp_path / "v.db"
    vault = LocalTokenVault(path, create=True)
    assert vault.created is True
    vault.discard_unwritten()
    vault.close()
    assert path.exists(), "ownership cannot be proven without a lock; the file must stay"


@posix_only
def test_a_locked_failed_run_that_created_the_vault_removes_it(tmp_path: Path) -> None:
    path = tmp_path / "v.db"
    vault = LocalTokenVault(path, create=True)
    vault.discard_unwritten()
    assert not path.exists()


def test_a_committed_run_is_never_discarded(tmp_path: Path) -> None:
    path = tmp_path / "v.db"
    vault = LocalTokenVault(path, create=True)
    vault.commit()
    vault.discard_unwritten()
    assert path.exists()


@posix_only
def test_a_failed_cleanup_unlink_neither_raises_nor_keeps_the_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "v.db"
    vault = LocalTokenVault(path, create=True)

    def _refuse(self: Path, missing_ok: bool = False) -> None:
        raise PermissionError(13, "denied")

    monkeypatch.setattr(Path, "unlink", _refuse)
    vault.discard_unwritten()  # must not raise
    monkeypatch.undo()
    assert path.exists()
    LocalTokenVault(path, create=True).close()  # the lock was released
