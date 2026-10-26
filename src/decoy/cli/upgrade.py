"""`decoy upgrade` -- re-run the verified installer to swap the managed runtime.

The self-hosted analogue of `pip install -U`: it queries the Decoy-hosted version
document, and if a newer (non-yanked) release exists, downloads that bundle, verifies
its checksum AND Ed25519 signature against the PINNED release key, lays the new runtime
down beside the current one, and swaps the ``current`` symlink atomically. The previous
version stays on disk for rollback, and a failed post-swap validation rolls ``current``
back automatically. A failed signature or checksum is a hard refusal.

This runs only inside a managed install (the bundled runtime under ``~/.decoy``). A
pip/dev checkout is told to use pip instead -- `decoy upgrade` does not touch an
environment it does not own.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import typer

from decoy import __version__
from decoy.cli.exit_codes import EXIT_OK, EXIT_RUNTIME, EXIT_USAGE
from decoy.distribution import installer, release_key
from decoy.distribution import version_document as vd
from decoy.ui.output import OutputMode, emit_json, setup_output
from decoy.ui.theme import error, hint, success

UPGRADE_EPILOG = """\
Examples:

  decoy upgrade
    Upgrade to the latest release if one is available.

  decoy upgrade --check
    Report whether a newer version exists; change nothing.

  decoy upgrade --version 0.2.0
    Install a specific version (downgrade or pin).

Verification: the version document and the bundle are both checked against the pinned
release key before anything is swapped. A bad signature or checksum refuses the upgrade.
"""

_DEFAULT_VERSION_URL = "https://decoy.dev/cli/version.json"


def _managed_home() -> Path | None:
    """The managed-runtime home IFF this interpreter is a bundled-runtime interpreter.

    A managed interpreter lives at ``<home>/versions/<version>/python``, so it locates
    its own home from ``sys.prefix`` (the nearest ancestor named ``versions`` -> its
    parent is the home). Deriving it from the running interpreter rather than from
    ``DECOY_HOME``/``~/.decoy`` means `decoy upgrade` works even when the install used a
    custom home and that env var is not set at upgrade time. Returns None for a pip/dev
    install (no ``versions`` ancestor)."""
    try:
        prefix = Path(sys.prefix).resolve()
    except OSError:
        return None
    for anc in prefix.parents:
        if anc.name == "versions":
            return anc.parent
    return None


def _fetch(url: str) -> bytes:
    import urllib.request

    with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310
        return resp.read()


def upgrade(
    version: str = typer.Option(None, "--version", help="Install this exact version instead of latest."),
    check: bool = typer.Option(False, "--check", help="Only report if a newer version exists."),
    force: bool = typer.Option(False, "--force", help="Reinstall even if already current."),
    url: str = typer.Option(None, "--url", help="Override the version-document URL.", hidden=True),
    json_: bool = typer.Option(False, "--json", help="Emit a JSON result."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress stdout."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Debug logs on stderr."),
) -> None:
    """Upgrade (or pin) the managed Decoy runtime from the Decoy-hosted channel."""
    state = setup_output(json_, quiet, verbose)

    home = _managed_home()
    if home is None:
        state.err_console.print(
            error("error:"),
            "`decoy upgrade` manages a bundled install, but this looks like a pip/dev install.",
        )
        state.err_console.print(" ", hint("hint:"), "upgrade it the way you installed it (e.g. `pip install -U decoy-cli`).")
        raise typer.Exit(code=EXIT_USAGE)

    try:
        pubkey = release_key.pinned_public_pem()
    except release_key.NoPinnedKeyError as exc:
        state.err_console.print(error("error:"), str(exc))
        raise typer.Exit(code=EXIT_USAGE) from exc

    doc_url = url or _DEFAULT_VERSION_URL
    try:
        doc_bytes = _fetch(doc_url)
        doc_sig = _fetch(doc_url + ".sig").decode("ascii").strip()
    except Exception as exc:  # noqa: BLE001
        state.err_console.print(error("error:"), f"could not reach the version endpoint: {exc}")
        raise typer.Exit(code=EXIT_RUNTIME) from exc

    if not vd.verify_document(doc_bytes, doc_sig, expected_public_pem=pubkey):
        state.err_console.print(error("error:"), "version-document signature INVALID -- refusing (possible tampering).")
        raise typer.Exit(code=EXIT_RUNTIME)
    doc = vd.parse_document(doc_bytes)
    latest = doc.get("latest")
    target_version = version or latest

    newer = vd.newer_available(__version__, doc)
    if check or (not force and not newer and version is None):
        if state.mode is OutputMode.json:
            emit_json(state, {
                "current": __version__, "latest": latest,
                "newer_available": bool(newer), "action": "none",
            })
        elif newer:
            state.console.print(success("update available:"), f"{__version__} -> {latest}. Run `decoy upgrade`.")
        else:
            state.console.print(success("up to date:"), f"decoy {__version__} is current.")
        raise typer.Exit(code=EXIT_OK)

    if not force and version is None and not newer:
        raise typer.Exit(code=EXIT_OK)

    def _post_swap(current: Path) -> bool:
        # Validate the swapped-in runtime actually launches and reports the new version.
        launcher = current / "decoy"
        try:
            out = subprocess.run([str(launcher), "--version"], capture_output=True, text=True, timeout=60)
        except Exception:  # noqa: BLE001
            return False
        return out.returncode == 0 and (target_version in out.stdout)

    try:
        outcome = installer.install_version(
            version_doc_bytes=doc_bytes,
            version_doc_sig_b64=doc_sig,
            expected_public_pem=pubkey,
            home=home,
            pin_version=version,
            download=_fetch,
            post_swap_validate=_post_swap,
        )
    except installer.InstallError as exc:
        state.err_console.print(error("error:"), str(exc))
        raise typer.Exit(code=EXIT_RUNTIME) from exc

    if state.mode is OutputMode.json:
        emit_json(state, {
            "current": outcome.version, "previous": outcome.previous_version,
            "target": outcome.target, "action": "upgraded",
        })
    else:
        state.console.print(
            success("upgraded:"),
            f"decoy {outcome.previous_version or '(none)'} -> {outcome.version} ({outcome.target}).",
        )
        if outcome.previous_version:
            state.console.print(" ", hint("rollback:"), f"decoy upgrade --version {outcome.previous_version}")
    raise typer.Exit(code=EXIT_OK)
