"""The `--vault` transaction of `decoy run`: usage and write errors, and the durable commit."""

from pathlib import Path

from decoy._atomic import destination_entry


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


VAULT_COMMIT_FAILED_HINT = (
    "the vault file was left in place and no output was written; remove the vault file "
    "before rerunning, or the rerun is refused with vault_exists."
)


def refuse_existing_vault(vault: Path) -> None:
    """Refuse a `--vault` path that is taken, before any source loads.

    Raises the engine's own `vault_exists` error so the text and exit code match the
    engine's refusal. The engine's exclusive link stays the authority: this only saves the
    masking work (and a leaked output) when the answer is already known.
    """
    import os

    from decoy_engine import VaultError, reasons

    if os.path.lexists(vault):
        raise VaultError(
            code=reasons.runtime.VAULT_EXISTS,
            message=reasons.get("runtime", reasons.runtime.VAULT_EXISTS).summary,
        )


def _commit_vault(vault_writer, vault: Path) -> None:
    """Publish the vault before any output: the engine owns the durable, exclusive publish.

    Engine 0.24.0 writes a private stage, fsyncs it, links it to the vault name (an existing
    vault is refused with `vault_exists`, never overwritten) and fsyncs the directory. Its
    own failures are coded and value-free and pass through. Any other failure is reported as
    the constant `vault_write_failed` text, because an OSError's text names the path.
    """
    from decoy_engine import VaultError

    failed = False
    try:
        vault_writer.write(destination_entry(vault))
    except VaultError:
        raise
    except Exception:
        failed = True
    if failed:
        # Raised outside the handler: an OSError's text names the path.
        raise _VaultWriteError(VAULT_WRITE_FAILED)
