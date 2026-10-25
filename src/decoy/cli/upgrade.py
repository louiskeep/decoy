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
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

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
) -> UpgradePlan:
    """Resolve the version to install and its artifact, or an error. Pure.

    A pinned `--version` wins; otherwise the document's `latest`. The artifact is
    the one for this host's target; a missing target or a missing artifact is a
    clear error, not a silent no-op (a user on an unsupported platform must be
    told, not left on an unchanged install thinking it upgraded)."""
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
    if pinned_version is None and resolved == current:
        return UpgradePlan(
            current=current,
            target=target,
            resolved_version=resolved,
            artifact=document.artifact_for(target),
            up_to_date=True,
            error=None,
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
# tests; the default shells out to the install script, which re-does the full
# checksum + signature verify before it extracts anything (packaging/install/).
InstallerRunner = Callable[[str, str, Artifact], None]


def perform_upgrade(plan: UpgradePlan, *, installer_runner: InstallerRunner) -> None:
    """Run the installer for a resolved plan. Raises on a plan that is not
    installable (its `error` set) so a caller never 'upgrades' to nothing."""
    if plan.error is not None or plan.resolved_version is None or plan.artifact is None:
        raise RuntimeError(plan.error or "upgrade plan is not installable")
    installer_runner(plan.resolved_version, plan.target or "", plan.artifact)


def _default_installer_runner(version: str, target: str, artifact: Artifact) -> None:
    """Fetch the install script and run it pinned to `version`.

    The install script does the verify-before-extract; this only locates it (a
    bundled copy via `DECOY_INSTALL_SCRIPT`, else downloaded from the artifact's
    host) and invokes it with `--version`. The base URL is derived from the
    artifact URL so the script fetches the matching bundle set."""
    script = os.environ.get("DECOY_INSTALL_SCRIPT")
    base_url = artifact.url.rsplit("/", 2)[0] if "/" in artifact.url else artifact.url
    env = dict(os.environ)
    env.setdefault("DECOY_INSTALL_BASE_URL", base_url)
    if script and Path(script).exists():
        subprocess.run(["sh", script, "--version", version], check=True, env=env)
        return
    import urllib.request

    with tempfile.TemporaryDirectory() as tmp:
        script_path = Path(tmp) / "install.sh"
        install_url = f"{base_url}/install.sh"
        with urllib.request.urlopen(install_url, timeout=30) as resp:
            script_path.write_bytes(resp.read())
        subprocess.run(["sh", str(script_path), "--version", version], check=True, env=env)


def upgrade(
    check: bool = typer.Option(
        False, "--check", help="Report whether a newer version exists; install nothing."
    ),
    version: str = typer.Option(
        "", "--version", help="Install a specific version instead of the latest."
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
    document = _version_endpoint.fetch_document(
        os.environ.get(_version_endpoint.UPDATE_URL_ENV) or _version_endpoint.DEFAULT_VERSION_URL
    )
    pinned = version or None
    plan = plan_upgrade(
        current=__version__, target=target, document=document, pinned_version=pinned
    )

    if check:
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
        perform_upgrade(plan, installer_runner=_default_installer_runner)
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
