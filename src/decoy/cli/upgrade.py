"""`decoy upgrade` -- upgrade the managed, self-hosted Decoy runtime.

Distribution is self-hosted bundles (B-2), so upgrading is re-running the
installer against the Decoy-hosted version document: it fetches the latest bundle
for this host's target, verifies its checksum and signature, and swaps the
`current` symlink to the new version. `--check` reports latest vs current without
installing.

The resolve-and-plan half (`plan_upgrade`) is a pure function and the install
half takes an injected runner, so the whole flow is testable without a network or
a real install (library code does not know its callers). The command body renders
and calls the real installer.
"""

from __future__ import annotations

import os
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

import typer
from rich.text import Text

from decoy import __version__, _version_endpoint
from decoy._version_endpoint import Artifact, VersionDocument
from decoy.cli.exit_codes import EXIT_OK, EXIT_RUNTIME, EXIT_USAGE
from decoy.ui.output import OutputMode, emit_json, setup_output
from decoy.ui.theme import error, hint, success

_UPGRADE_EPILOG = """\
Examples:

  decoy upgrade
    Install the latest matched runtime for this platform (verify, then swap).

  decoy upgrade --check
    Report whether a newer version is available; install nothing.

  decoy upgrade --version 0.2.0
    Install a specific version (pinned), for a reproducible environment.

Upgrade manages the self-hosted runtime under ~/.decoy. A bad checksum or
signature is a hard stop: nothing is installed. See packaging/README.md.
"""


@dataclass(frozen=True)
class UpgradePlan:
    """The resolved upgrade for this host, before anything is installed."""

    current: str
    target: str | None
    resolved_version: str | None
    artifact: Artifact | None
    up_to_date: bool
    error: str | None


def plan_upgrade(
    *,
    current: str,
    target: str | None,
    document: VersionDocument | None,
    pinned_version: str | None = None,
    allow_downgrade: bool = False,
) -> UpgradePlan:
    """Resolve the version to install and its artifact, or an error. Pure.

    A pinned `--version` wins; otherwise the document's `latest`. The artifact is
    the one for this host's target; a missing target or a missing artifact is a
    clear error, not a silent no-op (a user on an unsupported platform must be
    told, not left on an unchanged install thinking it upgraded).

    Direction is enforced: an unpinned upgrade only ever moves forward, so a
    document that serves a `latest` lower than the installed version (a signed
    rollback/replay) installs nothing. A non-newer build can only be installed by
    an explicit `--version`, and a true downgrade even then needs
    `allow_downgrade`. Versions are compared with PEP 440 (`_compare`)."""
    if target is None:
        return UpgradePlan(
            current=current,
            target=None,
            resolved_version=None,
            artifact=None,
            up_to_date=False,
            error=(
                "this platform has no Decoy bundle target. Supported: linux-x86_64, "
                "linux-aarch64, macos-arm64. See packaging/README.md."
            ),
        )
    if document is None:
        return UpgradePlan(
            current=current,
            target=target,
            resolved_version=None,
            artifact=None,
            up_to_date=False,
            error="could not reach the Decoy version endpoint. Try again, or check your network.",
        )
    resolved = pinned_version or document.latest
    if not resolved:
        return UpgradePlan(
            current=current,
            target=target,
            resolved_version=None,
            artifact=None,
            up_to_date=False,
            error="the version document names no latest version.",
        )
    if resolved in document.yanked:
        return UpgradePlan(
            current=current,
            target=target,
            resolved_version=resolved,
            artifact=None,
            up_to_date=False,
            error=(
                f"version {resolved} was withdrawn (yanked) and will not be installed. "
                "Upgrade to a current version instead."
            ),
        )
    direction = _version_endpoint._compare(resolved, current)
    if pinned_version is None:
        # Unpinned: only move forward. Equal, older, or incomparable means there
        # is nothing newer to install, so a served-lower `latest` is a no-op, not
        # a downgrade.
        if direction != 1:
            return UpgradePlan(
                current=current,
                target=target,
                resolved_version=resolved,
                artifact=document.artifact_for(target),
                up_to_date=True,
                error=None,
            )
    elif direction == -1 and not allow_downgrade:
        return UpgradePlan(
            current=current,
            target=target,
            resolved_version=resolved,
            artifact=None,
            up_to_date=False,
            error=(
                f"{resolved} is older than the installed {current}. Refusing to downgrade; "
                "pass --allow-downgrade to install an older build on purpose."
            ),
        )
    artifact = document.artifact_for(target)
    if artifact is None:
        return UpgradePlan(
            current=current,
            target=target,
            resolved_version=resolved,
            artifact=None,
            up_to_date=False,
            error=(
                f"version {resolved} has no bundle for {target}. It may not be "
                "published for this platform yet."
            ),
        )
    return UpgradePlan(
        current=current,
        target=target,
        resolved_version=resolved,
        artifact=artifact,
        up_to_date=False,
        error=None,
    )


# The installer runner performs the actual verify-and-swap. It is injected in
# tests; the default runs the LOCAL install script, which re-does the full
# checksum + signature verify before it extracts anything (packaging/install/).
# The runner also takes the version-endpoint URL so it can constrain the download
# to that same origin. A document must not be able to redirect the install.
InstallerRunner = Callable[[str, str, Artifact, str], None]

# The install script that ships with this CLI. It carries the release public key,
# so it IS the trust anchor and must never be fetched from a network location: a
# document-controlled host could otherwise serve its own script with its own key
# and defeat the signing chain. Shipped as package data in the wheel and read
# from packaging/ in a source checkout.
_PACKAGE_DIR = Path(__file__).resolve().parent.parent


def perform_upgrade(
    plan: UpgradePlan, *, version_url: str, installer_runner: InstallerRunner
) -> None:
    """Run the installer for a resolved plan. Raises on a plan that is not
    installable (its `error` set) so a caller never 'upgrades' to nothing.
    `version_url` is the origin the download is pinned to."""
    if plan.error is not None or plan.resolved_version is None or plan.artifact is None:
        raise RuntimeError(plan.error or "upgrade plan is not installable")
    installer_runner(plan.resolved_version, plan.target or "", plan.artifact, version_url)


def _same_origin(a: str, b: str) -> bool:
    """True if two URLs share a scheme, host, and port."""
    pa, pb = urlsplit(a), urlsplit(b)
    return (pa.scheme, pa.hostname, pa.port) == (pb.scheme, pb.hostname, pb.port)


def _local_install_script() -> Path:
    """Resolve the LOCAL install script, or raise. Never downloads it."""
    name = "install.ps1" if platform.system() == "Windows" else "install.sh"
    candidates = []
    override = os.environ.get("DECOY_INSTALL_SCRIPT")
    if override:
        candidates.append(Path(override))  # a local override, still never fetched
    candidates.append(_PACKAGE_DIR / "_packaging" / name)  # shipped in the wheel
    candidates.append(_PACKAGE_DIR.parents[1] / "packaging" / "install" / name)  # source tree
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError(
        "the bundled Decoy install script was not found. Refusing to download it: "
        "the script carries the release key and must be local. Reinstall the CLI."
    )


def _default_installer_runner(version: str, target: str, artifact: Artifact, version_url: str) -> None:
    """Run the LOCAL install script pinned to `version`, with the download
    constrained to the version endpoint's own origin.

    The install script does the verify-before-extract; this locates the local
    copy (never a download) and invokes it with `--version`. The artifact URL
    must be https and share the version endpoint's origin, and the base URL the
    script downloads from is pinned to that origin too, so a compromised or
    spoofed document cannot point the install at an attacker's host or key."""
    parsed = urlsplit(artifact.url)
    if parsed.scheme != "https":
        raise RuntimeError(
            f"refusing a non-https artifact URL ({artifact.url!r}); only https is allowed."
        )
    if not _same_origin(artifact.url, version_url):
        raise RuntimeError(
            f"the artifact origin ({parsed.scheme}://{parsed.netloc}) does not match the "
            "version endpoint origin. Refusing: a document must not redirect the install."
        )
    base_url = artifact.url.rsplit("/", 2)[0]
    env = dict(os.environ)
    override = env.get("DECOY_INSTALL_BASE_URL")
    if override:
        if urlsplit(override).scheme != "https" or not _same_origin(override, version_url):
            raise RuntimeError(
                "DECOY_INSTALL_BASE_URL must be https and the same origin as the version "
                "endpoint. Refusing a cross-origin download base."
            )
        base_url = override
    env["DECOY_INSTALL_BASE_URL"] = base_url

    script = _local_install_script()
    if script.suffix == ".ps1":
        cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Version", version]
    else:
        cmd = ["sh", str(script), "--version", version]
    subprocess.run(cmd, check=True, env=env)


def upgrade(
    check: bool = typer.Option(
        False, "--check", help="Report whether a newer version exists; install nothing."
    ),
    version: str = typer.Option(
        "", "--version", help="Install a specific version instead of the latest."
    ),
    allow_downgrade: bool = typer.Option(
        False,
        "--allow-downgrade",
        help="Permit installing an older version than the one installed (needs --version).",
    ),
    json_: bool = typer.Option(False, "--json", help="Emit a JSON record instead of text."),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug-level CLI logs on stderr."
    ),
) -> None:
    """Upgrade (or check) the managed, self-hosted Decoy runtime."""
    state = setup_output(json_, quiet, verbose)

    target = _version_endpoint.detect_target()
    version_url = (
        os.environ.get(_version_endpoint.UPDATE_URL_ENV) or _version_endpoint.DEFAULT_VERSION_URL
    )
    pinned = version or None

    if check:
        # Non-executing: report latest vs current. Tolerant parse is fine here
        # (nothing is installed from this path).
        document = _version_endpoint.fetch_document(version_url)
        decision = _version_endpoint.compute_update_decision(__version__, document)
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {
                    "command": "upgrade",
                    "status": "ok",
                    "action": "check",
                    "current": __version__,
                    "latest": decision.latest,
                    "target": target,
                    "update_available": decision.update_available,
                },
            )
            return
        if state.mode is OutputMode.quiet:
            return
        if decision.latest is None:
            state.err_console.print(hint("upgrade:"), "could not read the version endpoint.")
        elif decision.update_available:
            state.console.print(
                success(f"decoy {decision.latest} is available"),
                Text(f"(you have {__version__}). Run `decoy upgrade`."),
            )
        else:
            state.console.print(success(f"decoy {__version__} is up to date."))
        return

    # Executing path: the document is validated against the schema and fails
    # closed, so a malformed or unexpected shape never reaches an install.
    try:
        document: VersionDocument | None = _version_endpoint.fetch_document_validated(version_url)
        doc_error: str | None = None
    except _version_endpoint.VersionDocumentError as exc:
        document = None
        doc_error = str(exc)

    if doc_error is not None:
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {
                    "command": "upgrade",
                    "status": "error",
                    "current": __version__,
                    "target": target,
                    "error": doc_error,
                },
            )
            raise typer.Exit(code=EXIT_USAGE)
        state.err_console.print(error("upgrade:"), Text(doc_error))
        raise typer.Exit(code=EXIT_USAGE)

    plan = plan_upgrade(
        current=__version__,
        target=target,
        document=document,
        pinned_version=pinned,
        allow_downgrade=allow_downgrade,
    )

    if plan.error is not None:
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {
                    "command": "upgrade",
                    "status": "error",
                    "current": __version__,
                    "target": target,
                    "error": plan.error,
                },
            )
            raise typer.Exit(code=EXIT_USAGE)
        state.err_console.print(error("upgrade:"), Text(plan.error))
        raise typer.Exit(code=EXIT_USAGE)

    if plan.up_to_date:
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {
                    "command": "upgrade",
                    "status": "ok",
                    "action": "none",
                    "current": __version__,
                    "latest": plan.resolved_version,
                    "target": target,
                },
            )
            return
        if state.mode is not OutputMode.quiet:
            state.console.print(success(f"decoy {__version__} is already the latest."))
        return

    try:
        perform_upgrade(
            plan, version_url=version_url, installer_runner=_default_installer_runner
        )
    except Exception as exc:  # the installer failed; the runtime is unchanged.
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {
                    "command": "upgrade",
                    "status": "error",
                    "current": __version__,
                    "target": target,
                    "error": str(exc),
                },
            )
            raise typer.Exit(code=EXIT_RUNTIME) from exc
        state.err_console.print(error("upgrade:"), Text(f"install failed: {exc}"))
        state.err_console.print(
            " ", hint("hint:"), "your existing runtime is unchanged (verify-before-extract)."
        )
        raise typer.Exit(code=EXIT_RUNTIME) from exc

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "upgrade",
                "status": "ok",
                "action": "installed",
                "current": __version__,
                "installed": plan.resolved_version,
                "target": target,
            },
        )
        return
    if state.mode is not OutputMode.quiet:
        state.console.print(
            success(f"upgraded to decoy {plan.resolved_version}"),
            Text(f"for {target}. The managed runtime now matches."),
        )
    raise typer.Exit(code=EXIT_OK)


UPGRADE_EPILOG = _UPGRADE_EPILOG
