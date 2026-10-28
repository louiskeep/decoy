"""`decoy.cli._token_vault.LocalTokenVault` -- the local SQLite token store (B-1).

The store implements the engine's `TokenVaultWriter` protocol
(`lookup_existing` / `put`) for the tokenize path plus a `reverse` lookup for
detokenize. These tests pin its namespace scoping, idempotent/conflict write
behavior, the commit-on-success durability contract, and the fail-closed opens
detokenize relies on.
"""

from __future__ import annotations

import os
import sqlite3
import stat
import subprocess
import sys
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


# -- at-rest permissions (0600 file, 0700 created parent) -------------------

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX file modes")


def _mode(p: Path) -> int:
    return stat.S_IMODE(p.stat().st_mode)


@posix_only
def test_new_vault_is_0600_under_a_permissive_umask(tmp_path: Path) -> None:
    """Umask 0022 would leave a plain sqlite3.connect() file 0644, so only a real
    chmod yields 0600. Run in a subprocess so the umask never leaks into the
    test session."""
    vp = tmp_path / "t.db"
    code = (
        "import os, sys\n"
        "from pathlib import Path\n"
        "from decoy.cli._token_vault import LocalTokenVault\n"
        "os.umask(0o022)\n"
        "v = LocalTokenVault(Path(sys.argv[1]), create=True)\n"
        "v.put('ns', 'a', 'tok_1'); v.commit(); v.close()\n"
    )
    subprocess.run([sys.executable, "-c", code, str(vp)], check=True)
    assert _mode(vp) == 0o600


@posix_only
def test_reopen_repairs_a_0644_vault(tmp_path: Path) -> None:
    vp = tmp_path / "t.db"
    with LocalTokenVault(vp, create=True):
        pass
    vp.chmod(0o644)
    with LocalTokenVault(vp, create=True):
        pass
    assert _mode(vp) == 0o600


@posix_only
def test_created_parent_is_0700_and_preexisting_parent_untouched(tmp_path: Path) -> None:
    old = tmp_path / "shared"
    old.mkdir()
    old.chmod(0o755)
    with LocalTokenVault(old / "t.db", create=True):
        pass
    assert _mode(old) == 0o755

    new = tmp_path / "fresh"
    prev = os.umask(0o022)
    try:
        with LocalTokenVault(new / "t.db", create=True):
            pass
    finally:
        os.umask(prev)
    assert _mode(new) == 0o700


@posix_only
def test_chmod_failure_aborts_before_any_schema_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vp = tmp_path / "t.db"

    def boom(*_a: object, **_k: object) -> None:
        raise PermissionError("denied")

    monkeypatch.setattr(os, "chmod", boom)
    with pytest.raises(TokenVaultError) as exc:
        LocalTokenVault(vp, create=True)
    assert exc.value.code == "vault_permission_error"
    # No schema or data was written: the file is still the empty placeholder.
    assert vp.stat().st_size == 0


def test_schema_version_mismatch_fails_closed(tmp_path: Path) -> None:
    vp = tmp_path / "t.db"
    with LocalTokenVault(vp, create=True) as v:
        v.put("ns", "a", "tok_1")
        v.commit()
    conn = sqlite3.connect(str(vp))
    conn.execute("UPDATE meta SET value='999' WHERE key='schema_version'")
    conn.commit()
    conn.close()
    with pytest.raises(TokenVaultError) as exc:
        LocalTokenVault(vp, create=False)
    assert exc.value.code == "vault_schema_mismatch"
