"""Local token-vault store for `decoy tokenize` / `decoy detokenize` (B-1).

The engine's `tokenize` mask strategy (A-8 token-vault seam, engine ==0.15.1) derives a
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
plaintext, token)`) matches the engine's `TokenVaultWriter` Protocol
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
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path


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
        if not create and not path.exists():
            raise TokenVaultError(
                code="vault_not_found",
                message=(
                    f"token vault {path!s} does not exist; detokenize needs the "
                    "vault the tokenize run wrote. Pass the correct --vault path."
                ),
            )
        if create:
            parent = path.parent
            # Restrict only a directory THIS call creates; a pre-existing parent
            # may be a shared user directory we must not re-permission.
            parent_is_new = not parent.exists()
            parent.mkdir(parents=True, exist_ok=True)
            if parent_is_new:
                self._restrict(parent, 0o700)
            # Create the file 0600 up front so it is never briefly world-readable
            # under the process umask, then chmod on every create-path open to
            # repair a vault an earlier build left 0644. An empty file is a valid
            # new SQLite database. This precedes ALL schema/data writes: SQLite can
            # spill dirty pages mid-transaction, so protection cannot wait for
            # commit().
            try:
                os.close(os.open(path, os.O_RDWR | os.O_CREAT, 0o600))
            except OSError as exc:
                raise TokenVaultError(
                    code="vault_open_error",
                    message=f"could not create token vault {path!s}: {type(exc).__name__}.",
                ) from exc
            self._restrict(path, 0o600)
        try:
            # isolation_level="" keeps Python's implicit-transaction behavior:
            # the first write opens a transaction that stays open until an
            # explicit commit(), which is exactly the fail-closed contract. It is
            # the sqlite3 default, but passed explicitly so the contract does not
            # ride a library default the comment would otherwise misstate.
            self._conn = sqlite3.connect(str(path), isolation_level="")
        except sqlite3.Error as exc:
            raise TokenVaultError(
                code="vault_open_error",
                message=f"could not open token vault {path!s}: {type(exc).__name__}.",
            ) from exc
        self._ensure_schema(create=create)

    def _restrict(self, target: Path, mode: int) -> None:
        """chmod `target`, aborting the open if the restriction cannot be applied.

        The vault holds a cleartext re-identification map; proceeding with
        unrestricted perms would silently defeat its only at-rest protection.
        """
        try:
            os.chmod(target, mode)
        except OSError as exc:
            raise TokenVaultError(
                code="vault_permission_error",
                message=(
                    f"could not restrict permissions on {target!s} to "
                    f"{mode:04o}: {type(exc).__name__}; refusing to write the "
                    "token vault."
                ),
            ) from exc

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
            cur.execute(
                "INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', ?)",
                (str(_SCHEMA_VERSION),),
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
            ver = cur.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
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

    def put(self, namespace: str, plaintext: str, token: str) -> None:
        """Persist a newly minted `(plaintext, token)` pair under `namespace`.

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
                return
            raise TokenVaultError(
                code="vault_token_conflict",
                message=(
                    "the token vault already holds a different token for a value "
                    "in this namespace (likely a different mask key or a reused "
                    "vault); reversal would be ambiguous, so the run is aborted. "
                    "Use a fresh vault, or the mask secret the vault was built with."
                ),
            ) from None

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

    def close(self) -> None:
        """Close the connection, discarding any uncommitted writes."""
        self._conn.close()

    def __enter__(self) -> LocalTokenVault:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def iter_tokenize_columns(config_dict: dict, table_name: str) -> Iterator[tuple[str, str]]:
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
