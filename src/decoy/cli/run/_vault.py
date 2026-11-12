"""The `--vault` transaction of `decoy run`: usage and write errors, and the durable commit."""

import contextlib
import os
from pathlib import Path

from decoy._atomic import destination_entry, fsync_directory


class _VaultUsageError(Exception):
    """--vault on a config that cannot vault; user error (exits EXIT_USAGE)."""


VAULT_WRITE_FAILED = (
    "vault_write_failed: the vault could not be written durably, so no masked output was "
    "written. Check the vault's directory (free space, permissions) and re-run."
)


class _VaultWriteError(Exception):
    """The vault could not be made durable (exits EXIT_RUNTIME); its text is constant."""


class _ChunkedVaultError(Exception):
    """--chunked with --vault; user error (exits EXIT_USAGE).

    A chunked stream writes each output chunk before the vault that re-identifies it
    exists, so the engine refuses a chunked entry with a vault writer
    (`vault_requires_resident_output`). The CLI refuses first, before any work."""


_CHUNKED_VAULT_MESSAGE = (
    "chunked runs cannot write a token vault; rerun without --chunked or without --vault"
)


def _commit_vault(vault_writer, vault: Path) -> None:
    """Write the vault durably: 0600 temp file in its directory, fsync, rename, fsync the directory.

    The standard atomic-replace sequence (SQLite's rollback-journal commit and
    `ext4`'s documented rename guidance: data fsync, rename, directory fsync). Any failure
    leaves no temp file. A vault renamed in before a failed directory fsync is removed, and a
    pre-existing vault (kept as a hard link until the rename is durable) is put back, so a
    failed rewrite never loses the previous vault; a pre-existing vault that cannot be hard
    linked is not overwritten at all (the commit fails before the rename). Any failure is
    reported as the constant `vault_write_failed` text, except a coded engine `VaultError`
    (value-free, e.g. the install-the-vault-extra remedy), which keeps its own text after the
    same cleanup.
    """
    import secrets
    import tempfile

    from decoy_engine import VaultError

    tmp: Path | None = None
    backup: Path | None = None
    directory: Path | None = None
    renamed = False
    preserve_backup = False
    failed: BaseException | None = None
    try:
        # The temp, backup and rename must all use the entry selected by kernel parent lookup.
        vault = destination_entry(vault)
        directory = vault.parent
        fd, name = tempfile.mkstemp(prefix=f".{vault.name}.", suffix=".tmp", dir=directory)
        tmp = Path(name)
        os.close(fd)  # mkstemp made it 0600; the engine writer reopens it by path
        vault_writer.write(tmp)
        fd = os.open(tmp, os.O_RDWR)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        if os.path.lexists(vault):
            backup = directory / f".{vault.name}.{secrets.token_hex(8)}.bak"
            try:
                os.link(vault, backup, follow_symlinks=False)
            except OSError:
                # An existing vault that cannot be backed up is never overwritten: a failed
                # rename or directory fsync after it would leave neither vault.
                backup = None
                raise
        os.replace(tmp, vault)
        tmp, renamed = None, True
        fsync_directory(directory)
    except Exception as exc:
        failed = exc
    finally:
        if failed is not None and renamed:
            assert directory is not None
            try:
                if backup is not None:
                    os.replace(backup, vault)
                    backup = None
                else:
                    os.unlink(vault)
                fsync_directory(directory)
            except OSError:
                preserve_backup = backup is not None
        for leftover in (tmp, backup):
            if leftover is not None and not (preserve_backup and leftover == backup):
                with contextlib.suppress(OSError):
                    os.unlink(leftover)
    if isinstance(failed, VaultError):
        raise failed
    if failed is not None:
        # Raised outside the handler: an OSError's text names the path.
        raise _VaultWriteError(VAULT_WRITE_FAILED)
