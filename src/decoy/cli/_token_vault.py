"""Local token-vault store for `decoy tokenize` / `decoy detokenize` (B-1).

The engine's `tokenize` mask strategy (A-8 token-vault seam) derives a
deterministic surrogate per value and hands the `(plaintext, token)` pair to a
platform-injected writer; the engine holds no vault itself (library code does
not know its callers). This module is the CLI-side, single-operator, LOCAL
implementation of that writer: a SQLite file that persists the
`(namespace, plaintext) -> token` mapping and, for the reverse verb, looks a
plaintext back up by `(namespace, token)`.

Established methodology (CLAUDE.md core rule). There is NO hand-rolled crypto
here: the engine owns the token derivation (HKDF-SHA256 `derive`, see
`decoy_engine/execution/_strategies/_tokenize.py`) and the NFC normalization of
the plaintext key; this store only persists exactly what the engine hands to
`put` and returns it on `lookup_existing` / `reverse`. Persistence uses the
stdlib `sqlite3` embedded store -- the established local, atomic,
single-file key-value substrate -- rather than a bespoke on-disk format. The
protocol surface (`lookup_existing(namespace, plaintext)` / `put(namespace,
plaintext, token) -> str`) matches the engine's `TokenVaultWriter` Protocol
(`decoy_engine/execution/_adapter.py`), so the engine treats this store as the
opaque callback it expects.

Identity boundary. The vault is authoritative for identity: once a
`(namespace, plaintext)` pair has a token, the strategy REUSES it, so a value's
token is stable across jobs and key rotations. Both directions are scoped by
namespace, so the same plaintext under two namespaces is two distinct rows with
two distinct tokens, never one -- namespaces cannot be linked through a shared
token.

SECURITY: the vault file is the one place the plaintext-to-token mapping lives.
This module never prints or logs a plaintext or a token; callers surface counts
and column/namespace names only. Treat the file as sensitive -- it
re-identifies every tokenized value. It is cleartext at rest by design (no
encryption); the file is created 0600 (and a newly created parent dir 0700) as
the at-rest mitigation.

Concurrency. Every writer (`create=True`) takes an exclusive advisory lock on a sibling
`.<vault>.lock` before it creates or opens the vault and holds it until `close()`, so a second
writer is refused (`vault_busy`) and a failed run that created the file may delete it without
racing anyone. Readers (`create=False`: detokenize, unmask, report) take no lock; they read
only committed state. Where the platform has no advisory lock (Windows) ownership cannot be
proven, so a failed run leaves its empty vault and a re-run reuses it.
"""

from __future__ import annotations

import os
import secrets
import sqlite3
from collections.abc import Iterator
from pathlib import Path

from decoy._private_file import (
    PRIVATE_BUSY,
    PRIVATE_MODE_FAILED,
    PrivateFileError,
    advisory_lock_available,
    create_private_exclusive,
    lock_exclusive,
    open_private,
)


def _mint_scope() -> bytes:
    """A new vault's derivation scope. One seam so a test can fix it and compare tokens."""
    return secrets.token_bytes(_SCOPE_BYTES)


class TokenVaultError(Exception):
    """A coded, value-free failure of the local token vault.

    `code` is a stable machine token (mirrors the engine's error-code style);
    `message` never names a plaintext or a token, so it is safe to print and to
    ride into a `--json` error envelope.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# Bumped only on an incompatible on-disk change. Stored in `meta` so a
# detokenize against a future-format vault fails closed with a clear code
# rather than silently misreading rows.
_SCHEMA_VERSION = 1

# The engine derives every token under a per-vault, non-secret scope of 16 to 64 bytes that the
# vault's owner mints once (engine 0.24.0). This store is the owner: it mints the scope when it
# creates the vault and keeps it in `meta`. A vault with no scope predates the derivation; the
# engine refuses it, and this store never mints one into an existing vault.
_SCOPE_KEY = "derivation_scope"
_SCOPE_BYTES = 32


class LocalTokenVault:
    """SQLite-backed `(namespace, plaintext) <-> token` map.

    Implements the engine's `TokenVaultWriter` protocol (`lookup_existing` /
    `put`) for the forward tokenize path, plus `reverse` for the CLI-local
    detokenize path. Writes accumulate in one transaction and are made durable
    only by an explicit `commit()`, so a run that fails part-way leaves no
    partial mapping behind (fail-closed: no unrecorded output is paired with a
    half-written vault).
    """

    def __init__(self, path: Path, *, create: bool) -> None:
        """Open the vault at `path`.

        `create=True` (tokenize) makes the file and schema if absent;
        `create=False` (detokenize) fails closed with `vault_not_found` when
        the file is missing, so reversing against a vault that was never
        written is a clear coded error rather than an empty-map silent miss.
        """
        self._path = path
        # True only when THIS opener created the vault file; tokenize may delete only that.
        self.created = False
        self._lock_fd: int | None = None
        self._committed = False
        if not create and not path.exists():
            raise TokenVaultError(
                code="vault_not_found",
                message=(
                    f"token vault {path!s} does not exist; detokenize needs the "
                    "vault the tokenize run wrote. Pass the correct --vault path."
                ),
            )
        try:
            if create:
                parent = path.parent
                # Restrict only a directory THIS call creates; a pre-existing parent
                # may be a shared user directory we must not re-permission.
                parent_is_new = not parent.exists()
                parent.mkdir(parents=True, exist_ok=True)
                # The writer lock comes first: while this run holds it no other writer can
                # open the vault (every writer is create=True and locks first), so "this run
                # created the file and did not commit" is enough to delete it. Without an
                # advisory lock (Windows) ownership cannot be proven, so nothing is deleted.
                if advisory_lock_available():
                    lock_failure: PrivateFileError | None = None
                    try:
                        self._lock_fd = lock_exclusive(path.with_name(f".{path.name}.lock"))
                    except PrivateFileError as exc:
                        lock_failure = exc
                    if lock_failure is not None:
                        if lock_failure.code == PRIVATE_BUSY:
                            raise TokenVaultError(
                                code="vault_busy",
                                message=(
                                    "another decoy run is writing this token vault; "
                                    "wait for it to finish or use a different --vault."
                                ),
                            )
                        raise TokenVaultError(
                            code="vault_open_error",
                            message=f"could not lock token vault {path!s}: {lock_failure.code}.",
                        )
                # Exclusive create decides "this run made the file", under the lock.
                self.created = create_private_exclusive(path)
                # open_private creates the file 0600 before any schema write (SQLite can
                # spill dirty pages mid-transaction, so protection cannot wait for
                # commit()), repairs a vault an earlier build left 0644, and narrows a
                # parent this call created to 0700. An empty file is a valid new database.
                try:
                    open_private(path, new_parent=parent_is_new)
                except PrivateFileError as exc:
                    if exc.code == PRIVATE_MODE_FAILED:
                        raise TokenVaultError(
                            code="vault_permission_error",
                            message=(
                                "could not restrict permissions on the token vault: "
                                f"{exc.code}; refusing to write the token vault."
                            ),
                        ) from None
                    raise TokenVaultError(
                        code="vault_open_error",
                        message=f"could not create token vault {path!s}: {exc.code}.",
                    ) from None
            open_failure: sqlite3.Error | None = None
            try:
                # isolation_level="" keeps Python's implicit-transaction behavior:
                # the first write opens a transaction that stays open until an
                # explicit commit(), which is exactly the fail-closed contract. It is
                # the sqlite3 default, but passed explicitly so the contract does not
                # ride a library default the comment would otherwise misstate.
                self._conn = sqlite3.connect(str(path), isolation_level="")
            except sqlite3.Error as exc:
                open_failure = exc
            if open_failure is not None:
                raise TokenVaultError(
                    code="vault_open_error",
                    message=f"could not open token vault {path!s}: {type(open_failure).__name__}.",
                )
            self._ensure_schema(create=create)
        except BaseException as exc:
            # No object exists to ask, so a failure that left this run holding a vault it
            # created hands the caller `vault_discard`, which removes the stub under the lock.
            # Any other failure releases the lock here.
            if self.created and self._lock_fd is not None:
                exc.vault_discard = self.discard_unwritten  # type: ignore[attr-defined]
            else:
                self._release_lock()
            raise

    @property
    def derivation_scope(self) -> bytes | None:
        """The vault's token-derivation scope, or None for a vault written without one."""
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key = ?", (_SCOPE_KEY,)
        ).fetchone()
        return bytes.fromhex(row[0]) if row is not None else None

    def _ensure_schema(self, *, create: bool) -> None:
        cur = self._conn.cursor()
        if create:
            cur.executescript(
                """
                CREATE TABLE IF NOT EXISTS token_map (
                    namespace TEXT NOT NULL,
                    plaintext TEXT NOT NULL,
                    token     TEXT NOT NULL,
                    PRIMARY KEY (namespace, plaintext)
                );
                CREATE INDEX IF NOT EXISTS idx_token_reverse
                    ON token_map (namespace, token);
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            fresh = cur.execute("SELECT 1 FROM meta WHERE key = 'schema_version'").fetchone() is None
            cur.execute(
                "INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', ?)",
                (str(_SCHEMA_VERSION),),
            )
            if fresh:
                # OR IGNORE: a concurrent opener that also saw an empty meta table may have
                # committed its scope first; keep that one so both runs share it.
                cur.execute(
                    "INSERT OR IGNORE INTO meta (key, value) VALUES (?, ?)",
                    (_SCOPE_KEY, _mint_scope().hex()),
                )
            # The schema itself is durable immediately; only DATA rows wait for
            # the caller's commit() so a failed run leaves an empty vault, not a
            # partial mapping.
            self._conn.commit()
        else:
            # A pre-existing file that is not one of our vaults (not a SQLite
            # database at all, no token_map, or a newer schema) must fail
            # closed, not reverse to all-misses.
            try:
                row = cur.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='token_map'"
                ).fetchone()
            except sqlite3.DatabaseError as exc:
                raise TokenVaultError(
                    code="vault_not_a_token_vault",
                    message=(
                        f"{self._path!s} is not a decoy token vault "
                        "(not a readable SQLite database); pass the vault the "
                        "tokenize run wrote."
                    ),
                ) from exc
            if row is None:
                raise TokenVaultError(
                    code="vault_not_a_token_vault",
                    message=(
                        f"{self._path!s} is not a decoy token vault "
                        "(no token_map table); pass the vault the tokenize run wrote."
                    ),
                )
            ver = cur.execute(
                "SELECT value FROM meta WHERE key='schema_version'"
            ).fetchone()
            if ver is not None and ver[0] != str(_SCHEMA_VERSION):
                raise TokenVaultError(
                    code="vault_schema_mismatch",
                    message=(
                        f"token vault {self._path!s} was written under schema "
                        f"version {ver[0]}, but this CLI reads version "
                        f"{_SCHEMA_VERSION}; re-tokenize under the current CLI."
                    ),
                )

    # -- engine TokenVaultWriter protocol -----------------------------------

    def lookup_existing(self, namespace: str, plaintext: str) -> str | None:
        """The token already stored for `(namespace, plaintext)`, or None."""
        row = self._conn.execute(
            "SELECT token FROM token_map WHERE namespace = ? AND plaintext = ?",
            (namespace, plaintext),
        ).fetchone()
        return row[0] if row is not None else None

    def put(self, namespace: str, plaintext: str, token: str) -> str:
        """Persist a newly minted `(plaintext, token)` pair under `namespace` and
        return the stored token, which the engine (>=0.16.0) emits; it fails the
        run closed on a None return.

        The engine only calls this after `lookup_existing` returned None, so a
        row should not already exist. If one does with the SAME token the write
        is idempotent (a no-op); a DIFFERENT token means this vault already
        holds a mapping for the value under another mask key -- reusing it would
        make the two tokens irreversible against each other, so it fails closed
        rather than overwrite. The engine wraps any exception raised here into
        its own value-free `tokenize_vault_error`, aborting the run.
        """
        try:
            self._conn.execute(
                "INSERT INTO token_map (namespace, plaintext, token) VALUES (?, ?, ?)",
                (namespace, plaintext, token),
            )
        except sqlite3.IntegrityError:
            existing = self.lookup_existing(namespace, plaintext)
            if existing == token:
                return token
            raise TokenVaultError(
                code="vault_token_conflict",
                message=(
                    "the token vault already holds a different token for a value "
                    "in this namespace (likely a different mask key or a reused "
                    "vault); reversal would be ambiguous, so the run is aborted. "
                    "Use a fresh vault, or the mask secret the vault was built with."
                ),
            ) from None
        return token

    # -- CLI-local reverse path (detokenize) --------------------------------

    def reverse(self, namespace: str, token: str) -> str | None:
        """The plaintext stored for `(namespace, token)`, or None on a miss.

        A miss means this `(namespace, token)` pair was never written to this
        vault -- a wrong vault, a wrong namespace, or a value that was not
        tokenized. The caller decides policy (detokenize fails closed on any
        miss rather than emit a value it cannot vouch for).
        """
        row = self._conn.execute(
            "SELECT plaintext FROM token_map WHERE namespace = ? AND token = ?",
            (namespace, token),
        ).fetchone()
        return row[0] if row is not None else None

    def count(self) -> int:
        """Number of stored `(namespace, plaintext) -> token` rows."""
        return int(self._conn.execute("SELECT COUNT(*) FROM token_map").fetchone()[0])

    def commit(self) -> None:
        """Make accumulated writes durable. Call only after the run succeeds."""
        self._conn.commit()
        self._committed = True

    def _release_lock(self) -> None:
        if self._lock_fd is not None:
            os.close(self._lock_fd)
            self._lock_fd = None

    def discard_unwritten(self) -> None:
        """Remove the vault file when this run created it, holds the lock, and never committed.

        The lock was taken before the file was created, so no other run can have opened or
        committed to it. Without a lock the file is left for a re-run to reuse. Always
        releases the lock.
        """
        try:
            if self.created and self._lock_fd is not None and not self._committed:
                conn = getattr(self, "_conn", None)
                if conn is not None:
                    conn.close()
                self._path.unlink(missing_ok=True)
        finally:
            self._release_lock()

    def close(self) -> None:
        """Close the connection, discarding any uncommitted writes, and release the lock."""
        try:
            self._conn.close()
        finally:
            self._release_lock()

    def __enter__(self) -> LocalTokenVault:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def iter_tokenize_columns(
    config_dict: dict, table_name: str
) -> Iterator[tuple[str, str]]:
    """Yield `(column, namespace)` for each `strategy: tokenize` column of a table.

    Reads the validated config dump. The engine REQUIRES an explicit namespace
    on every tokenize column (it fails closed with `tokenize_requires_namespace`
    otherwise), so a tokenize column that reaches a successful run always has
    one here -- which is exactly the namespace detokenize must key its reverse
    lookup on. A tokenize column missing `namespace` in the config is yielded
    with an empty string so the caller can report the same fail-closed reason
    the engine would, before touching the vault.
    """
    for table in config_dict.get("tables") or []:
        if not isinstance(table, dict) or table.get("name") != table_name:
            continue
        for col in table.get("columns") or []:
            if isinstance(col, dict) and col.get("strategy") == "tokenize":
                yield col["name"], (col.get("namespace") or "")
