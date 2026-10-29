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
from pathlib import Path

import typer

from decoy import __version__
from decoy.cli.exit_codes import EXIT_OK, EXIT_RUNTIME, EXIT_USAGE
from decoy.distribution import installer, layout, release_key
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
    """The managed-runtime home, or None for a pip/dev install (see `layout.managed_home`)."""
    return layout.managed_home()


def _fetch(url: str) -> bytes:
    import urllib.request

    with urllib.request.urlopen(url, timeout=30) as resp:
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

    # Local rollback must not depend on the network. An explicit `--version <v>` that is
    # already installed on disk is activated via an atomic `current`-pointer swap with no
    # download, so a version-endpoint outage never blocks rolling back to already-verified
    # bits. Resolved BEFORE any fetch. `--force` is excluded on purpose: a forced reinstall
    # is a repair -- it must re-download and re-verify, not swap to the retained runtime.
    # `--check` is excluded too: it is READ-ONLY (report whether a newer version exists),
    # so it must never activate -- i.e. swap `current` and rewrite the launcher. It falls
    # through to the check-and-report branch below.
    if version is not None and not force and not check and installer.local_version_present(version, home):
        try:
            outcome = installer.activate_local_version(version, home=home, expected_public_pem=pubkey)
        except installer.InstallError as exc:
            state.err_console.print(error("error:"), str(exc))
            raise typer.Exit(code=EXIT_RUNTIME) from exc
        _report_outcome(state, outcome, "activated")
        raise typer.Exit(code=EXIT_OK)

    doc_url = url or _DEFAULT_VERSION_URL
    try:
        doc_bytes = _fetch(doc_url)
        doc_sig = _fetch(doc_url + ".sig").decode("ascii").strip()
    except Exception as exc:
        state.err_console.print(error("error:"), f"could not reach the version endpoint: {exc}")
        raise typer.Exit(code=EXIT_RUNTIME) from exc

    if not vd.verify_document(doc_bytes, doc_sig, expected_public_pem=pubkey):
        state.err_console.print(error("error:"), "version-document signature INVALID -- refusing (possible tampering).")
        raise typer.Exit(code=EXIT_RUNTIME)
    try:
        doc = vd.parse_document(doc_bytes)
    except ValueError as exc:
        state.err_console.print(error("error:"), f"version document rejected: {exc}")
        raise typer.Exit(code=EXIT_RUNTIME) from exc
    try:
        # --check is read-only, so it enforces freshness but does not advance the state.
        installer.check_document_freshness(doc, home, record=False)
    except installer.InstallError as exc:
        state.err_console.print(error("error:"), str(exc))
        raise typer.Exit(code=EXIT_RUNTIME) from exc
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
        except Exception:
            return False
        return out.returncode == 0 and target_version is not None and target_version in out.stdout

    # A local activation was already handled before the network fetch (above). Everything
    # that reaches here downloads + re-verifies: a plain/latest upgrade, a pinned
    # not-yet-installed version, and a `--force` reinstall (a repair, even of a version
    # already on disk -- so a same-version `--force` re-downloads and re-verifies rather
    # than swapping to the retained bits).
    try:
        # The base the version document was served under; a pinned non-latest version
        # resolves <base>/<version>/decoy-<version>-<target>.tar.gz (install.sh scheme).
        base_url = doc_url.rsplit("/", 1)[0]
        outcome = installer.install_version(
            version_doc_bytes=doc_bytes,
            version_doc_sig_b64=doc_sig,
            expected_public_pem=pubkey,
            home=home,
            pin_version=version,
            base_url=base_url,
            download=_fetch,
            post_swap_validate=_post_swap,
        )
    except installer.InstallError as exc:
        state.err_console.print(error("error:"), str(exc))
        raise typer.Exit(code=EXIT_RUNTIME) from exc

    _report_outcome(state, outcome, "upgraded")
    raise typer.Exit(code=EXIT_OK)


def _report_outcome(state, outcome, action: str) -> None:
    """Emit the install/activation result (JSON or human), with the rollback hint."""
    if state.mode is OutputMode.json:
        emit_json(state, {
            "current": outcome.version, "previous": outcome.previous_version,
            "target": outcome.target, "action": action,
        })
        return
    state.console.print(
        success(f"{action}:"),
        f"decoy {outcome.previous_version or '(none)'} -> {outcome.version} ({outcome.target}).",
    )
    # The rollback hint points at the retained previous runtime; `decoy upgrade
    # --version <previous>` activates it in place (local swap), it does not re-download.
    if outcome.rollback_version:
        state.console.print(" ", hint("rollback:"), f"decoy upgrade --version {outcome.rollback_version}")
