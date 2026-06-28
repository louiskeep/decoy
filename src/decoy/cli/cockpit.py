"""`decoy strategies`, `decoy providers`, `decoy checksums`, `decoy validators`,
and `decoy doctor` -- engine cockpit: live registry introspection + health check.

All list/inspect commands read the REAL engine registry at runtime. No
provider names, strategy names, checksum schemes, or validator names are
hardcoded in this module. If the engine adds or removes an entry, the CLI
surfaces it automatically without a CLI code change.

Registry sources (all resolved at import time of the engine sub-package,
not of this module):

  Strategies  : decoy_engine.execution._strategies.SCALAR_HANDLERS
  Providers   : decoy_engine.providers_v2.get_default_registry()
  Checksums   : decoy_engine.checksums._KNOWN_SCHEMES
  Validators  : decoy_engine.validators._registry._REGISTRY

`decoy doctor` checks hard and optional engine dependencies and exits
non-zero when any hard requirement is missing.
"""

from __future__ import annotations

import importlib.util
import sys

import typer

from decoy.cli.exit_codes import EXIT_RUNTIME, EXIT_USAGE
from decoy.ui.output import OutputMode, emit_json, setup_output
from decoy.ui.table import make_table
from decoy.ui.theme import accent, code, error, hint, success, warn

# ---------------------------------------------------------------------------
# strategies sub-app
# ---------------------------------------------------------------------------

strategies_app = typer.Typer(
    name="strategies",
    help="Enumerate and inspect the engine's registered mask strategies.",
    no_args_is_help=True,
)

_STRATEGIES_LIST_EPILOG = """\
Examples:

  decoy strategies list
    Print every registered mask strategy with its class name.

  decoy strategies list --json
    Same data as JSON for CI or support tooling.

See also: decoy strategies inspect, decoy providers list.
"""

_STRATEGIES_INSPECT_EPILOG = """\
Examples:

  decoy strategies inspect fpe
    Show parameters and behavior for the FPE strategy.

  decoy strategies inspect geo_generalize --json
    Same data as JSON.

See also: decoy strategies list.
"""


def _strategies_list(
    json_: bool = typer.Option(
        False,
        "--json",
        help="Emit a JSON list of registered strategies instead of a table.",
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug-level CLI logs on stderr."
    ),
) -> None:
    """List every registered mask strategy in the engine."""
    state = setup_output(json_, quiet, verbose)

    # Read the REAL engine registry at runtime.
    from decoy_engine.execution._strategies import SCALAR_HANDLERS

    entries = [
        {"name": name, "class": type(handler).__name__}
        for name, handler in sorted(SCALAR_HANDLERS.items())
    ]

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "strategies list",
                "status": "ok",
                "count": len(entries),
                "strategies": entries,
            },
        )
        return

    if state.mode is OutputMode.quiet:
        return

    state.console.print(accent(f"Registered mask strategies ({len(entries)}):"))
    table = make_table("Name", "Class")
    for e in entries:
        table.add_row(e["name"], e["class"])
    state.console.print(table)
    state.console.print()
    state.console.print(
        hint("Tip:"),
        "inspect one with",
        code("decoy strategies inspect <name>") + ".",
    )


def _strategies_inspect(
    name: str = typer.Argument(..., help="Strategy name to inspect."),
    json_: bool = typer.Option(
        False,
        "--json",
        help="Emit a JSON record instead of a panel.",
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug-level CLI logs on stderr."
    ),
) -> None:
    """Show details for one registered mask strategy."""
    state = setup_output(json_, quiet, verbose)

    from decoy_engine.execution._strategies import SCALAR_HANDLERS

    handler = SCALAR_HANDLERS.get(name)
    if handler is None:
        known = sorted(SCALAR_HANDLERS.keys())
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {
                    "command": "strategies inspect",
                    "status": "error",
                    "name": name,
                    "error": f"unknown strategy {name!r}",
                    "known": known,
                },
            )
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), f"unknown strategy {name!r}.")
            state.err_console.print(
                " ",
                hint("hint:"),
                "list strategies with",
                code("decoy strategies list") + ".",
            )
        raise typer.Exit(code=EXIT_USAGE)

    cls = type(handler)
    # First non-blank line of the handler class docstring -- true facts only.
    class_doc = (cls.__doc__ or "").strip()
    summary = class_doc.splitlines()[0].strip() if class_doc else ""

    record = {
        "name": name,
        "class": cls.__name__,
        "module": cls.__module__,
        "summary": summary,
    }

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {"command": "strategies inspect", "status": "ok", **record},
        )
        return

    if state.mode is OutputMode.quiet:
        return

    state.console.print(accent(f"Strategy: {name}"))
    table = make_table("Field", "Value")
    table.add_row("name", name)
    table.add_row("class", cls.__name__)
    table.add_row("module", cls.__module__)
    if summary:
        table.add_row("summary", summary)
    state.console.print(table)
    state.console.print()
    state.console.print(
        hint("See also:"),
        code("decoy strategies list") + ".",
    )


strategies_app.command(name="list", epilog=_STRATEGIES_LIST_EPILOG)(_strategies_list)
strategies_app.command(name="inspect", epilog=_STRATEGIES_INSPECT_EPILOG)(_strategies_inspect)


# ---------------------------------------------------------------------------
# providers sub-app
# ---------------------------------------------------------------------------

providers_app = typer.Typer(
    name="providers",
    help="Enumerate and inspect the engine's registered generation providers.",
    no_args_is_help=True,
)

_PROVIDERS_LIST_EPILOG = """\
Examples:

  decoy providers list
    Print every registered provider with backend type and poolable flag.

  decoy providers list --json
    Same data as JSON.

See also: decoy providers inspect, decoy strategies list.
"""

_PROVIDERS_INSPECT_EPILOG = """\
Examples:

  decoy providers inspect person_name
    Show capability matrix for the person_name provider.

  decoy providers inspect synthetic_ssn --json
    Same data as JSON.

See also: decoy providers list.
"""


def _providers_list(
    json_: bool = typer.Option(
        False,
        "--json",
        help="Emit a JSON list of registered providers instead of a table.",
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug-level CLI logs on stderr."
    ),
) -> None:
    """List every registered generation provider in the engine."""
    state = setup_output(json_, quiet, verbose)

    # Read the REAL engine registry at runtime.
    from decoy_engine.providers_v2 import get_default_registry

    registry = get_default_registry()
    provider_names = sorted(registry.known_providers())
    entries = []
    for pname in provider_names:
        cap = registry.get_capabilities(pname)
        entries.append(
            {
                "name": pname,
                "backend_type": cap.backend_type,
                "poolable": cap.poolable,
                "supports_deterministic": cap.supports_deterministic,
                "participates_in_fk_pk": cap.participates_in_fk_pk,
            }
        )

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "providers list",
                "status": "ok",
                "count": len(entries),
                "providers": entries,
            },
        )
        return

    if state.mode is OutputMode.quiet:
        return

    state.console.print(accent(f"Registered providers ({len(entries)}):"))
    table = make_table("Name", "Backend", "Poolable", "Det.", "FK/PK")
    for e in entries:
        table.add_row(
            e["name"],
            e["backend_type"],
            "yes" if e["poolable"] else "no",
            "yes" if e["supports_deterministic"] else "no",
            "yes" if e["participates_in_fk_pk"] else "no",
        )
    state.console.print(table)
    state.console.print()
    state.console.print(
        hint("Tip:"),
        "inspect one with",
        code("decoy providers inspect <name>") + ".",
    )


def _providers_inspect(
    name: str = typer.Argument(..., help="Provider name to inspect."),
    json_: bool = typer.Option(
        False,
        "--json",
        help="Emit a JSON record instead of a panel.",
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug-level CLI logs on stderr."
    ),
) -> None:
    """Show capability details for one registered provider."""
    state = setup_output(json_, quiet, verbose)

    from decoy_engine.providers_v2 import get_default_registry

    registry = get_default_registry()

    if not registry.has(name):
        known = sorted(registry.known_providers())
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {
                    "command": "providers inspect",
                    "status": "error",
                    "name": name,
                    "error": f"unknown provider {name!r}",
                    "known": known,
                },
            )
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), f"unknown provider {name!r}.")
            state.err_console.print(
                " ",
                hint("hint:"),
                "list providers with",
                code("decoy providers list") + ".",
            )
        raise typer.Exit(code=EXIT_USAGE)

    cap = registry.get_capabilities(name)
    record = {
        "name": cap.provider,
        "backend_type": cap.backend_type,
        "backend_version": cap.backend_version,
        "supports_deterministic": cap.supports_deterministic,
        "supports_uniqueness": cap.supports_uniqueness,
        "supports_value_reuse": cap.supports_value_reuse,
        "preserves_source_cardinality": cap.preserves_source_cardinality,
        "participates_in_fk_pk": cap.participates_in_fk_pk,
        "poolable": cap.poolable,
        "supported_locales": list(cap.supported_locales),
        "supports_coherent_link": cap.supports_coherent_link,
        "format_regex": cap.format_regex,
        "blocklist_validators": list(cap.blocklist_validators),
        "fallback_behavior": cap.fallback_behavior,
    }

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {"command": "providers inspect", "status": "ok", **record},
        )
        return

    if state.mode is OutputMode.quiet:
        return

    state.console.print(accent(f"Provider: {name}"))
    table = make_table("Field", "Value")
    for field_name, value in record.items():
        table.add_row(field_name, str(value))
    state.console.print(table)
    state.console.print()
    state.console.print(
        hint("See also:"),
        code("decoy providers list") + ".",
    )


providers_app.command(name="list", epilog=_PROVIDERS_LIST_EPILOG)(_providers_list)
providers_app.command(name="inspect", epilog=_PROVIDERS_INSPECT_EPILOG)(_providers_inspect)


# ---------------------------------------------------------------------------
# checksums sub-app
# ---------------------------------------------------------------------------

checksums_app = typer.Typer(
    name="checksums",
    help="List the engine's registered checksum schemes (SP-04).",
    no_args_is_help=True,
)

_CHECKSUMS_LIST_EPILOG = """\
Examples:

  decoy checksums list
    Print every registered checksum scheme.

  decoy checksums list --json
    Same data as JSON.

See also: decoy validators list.
"""


def _checksums_list(
    json_: bool = typer.Option(
        False,
        "--json",
        help="Emit a JSON list of checksum scheme names.",
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug-level CLI logs on stderr."
    ),
) -> None:
    """List every registered checksum scheme in the engine (SP-04)."""
    state = setup_output(json_, quiet, verbose)

    # Read the REAL engine registry at runtime.
    from decoy_engine.checksums import _KNOWN_SCHEMES

    schemes = sorted(_KNOWN_SCHEMES)

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "checksums list",
                "status": "ok",
                "count": len(schemes),
                "schemes": schemes,
            },
        )
        return

    if state.mode is OutputMode.quiet:
        return

    state.console.print(accent(f"Registered checksum schemes ({len(schemes)}):"))
    table = make_table("Scheme")
    for scheme in schemes:
        table.add_row(scheme)
    state.console.print(table)
    state.console.print()
    state.console.print(
        hint("See also:"),
        code("decoy validators list") + ".",
    )


checksums_app.command(name="list", epilog=_CHECKSUMS_LIST_EPILOG)(_checksums_list)


# ---------------------------------------------------------------------------
# validators sub-app
# ---------------------------------------------------------------------------

validators_app = typer.Typer(
    name="validators",
    help="List the engine's registered job-level validators (SP-05).",
    no_args_is_help=True,
)

_VALIDATORS_LIST_EPILOG = """\
Examples:

  decoy validators list
    Print every registered job-level validator.

  decoy validators list --json
    Same data as JSON.

See also: decoy checksums list.
"""


def _validators_list(
    json_: bool = typer.Option(
        False,
        "--json",
        help="Emit a JSON list of validator names.",
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug-level CLI logs on stderr."
    ),
) -> None:
    """List every registered job-level validator in the engine (SP-05)."""
    state = setup_output(json_, quiet, verbose)

    # Read the REAL engine registry at runtime.
    from decoy_engine.validators._registry import _REGISTRY

    validator_names = sorted(_REGISTRY.keys())

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "validators list",
                "status": "ok",
                "count": len(validator_names),
                "validators": validator_names,
            },
        )
        return

    if state.mode is OutputMode.quiet:
        return

    state.console.print(accent(f"Registered validators ({len(validator_names)}):"))
    table = make_table("Name")
    for vname in validator_names:
        table.add_row(vname)
    state.console.print(table)
    state.console.print()
    state.console.print(
        hint("See also:"),
        code("decoy checksums list") + ".",
    )


validators_app.command(name="list", epilog=_VALIDATORS_LIST_EPILOG)(_validators_list)


# ---------------------------------------------------------------------------
# doctor command
# ---------------------------------------------------------------------------

_DOCTOR_EPILOG = """\
Examples:

  decoy doctor
    Run all environment health checks and print a report.

  decoy doctor --json
    Same data as JSON for CI or support tooling.

  decoy doctor --quiet
    Silent mode; exit code 0 = healthy, non-zero = hard requirement missing.

See also: decoy --version, decoy info.
"""

# Hard requirements: must pass or decoy cannot function.
# Soft requirements: warn when absent but do not fail.
_HARD_REQS = ["decoy_engine"]
_SOFT_REQS = ["pyarrow", "polars", "lark", "stdnum"]


def _check_importable(pkg: str) -> tuple[bool, str]:
    """Return (present, version_or_note)."""
    try:
        spec = importlib.util.find_spec(pkg)
        if spec is None:
            return False, "not found"
        mod = importlib.import_module(pkg)
        version = getattr(mod, "__version__", "")
        return True, version if version else "present"
    except Exception as exc:
        return False, f"import error: {exc}"


def doctor(
    json_: bool = typer.Option(
        False,
        "--json",
        help="Emit a JSON health report instead of a table.",
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug-level CLI logs on stderr."
    ),
) -> None:
    """Check engine and dependency health.

    Exits 0 when all hard requirements are present. Exits non-zero when a
    hard requirement is missing. Soft-requirement absences produce warnings
    but do not change the exit code.
    """
    state = setup_output(json_, quiet, verbose)

    checks: list[dict] = []

    # Python version -- informational, always passes.
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    checks.append(
        {
            "name": "python",
            "kind": "info",
            "status": "pass",
            "note": py_ver,
        }
    )

    # CLI version -- informational, always passes.
    from decoy import __version__ as cli_version

    checks.append(
        {
            "name": "decoy-cli",
            "kind": "info",
            "status": "pass",
            "note": cli_version,
        }
    )

    # Hard requirements.
    hard_failed: list[str] = []
    for pkg in _HARD_REQS:
        present, note = _check_importable(pkg)
        status = "pass" if present else "fail"
        if not present:
            hard_failed.append(pkg)
        checks.append({"name": pkg, "kind": "hard", "status": status, "note": note})

    # Soft requirements.
    for pkg in _SOFT_REQS:
        present, note = _check_importable(pkg)
        status = "pass" if present else "warn"
        checks.append({"name": pkg, "kind": "soft", "status": status, "note": note})

    overall = "fail" if hard_failed else "pass"

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "doctor",
                "status": overall,
                "checks": checks,
                "hard_failed": hard_failed,
            },
        )
        if hard_failed:
            raise typer.Exit(code=EXIT_RUNTIME)
        return

    if state.mode is OutputMode.quiet:
        if hard_failed:
            raise typer.Exit(code=EXIT_RUNTIME)
        return

    state.console.print(accent("Decoy environment health:"))
    table = make_table("Check", "Kind", "Status", "Note")
    for c in checks:
        if c["status"] == "pass":
            status_text = success("pass")
        elif c["status"] == "warn":
            status_text = warn("warn")
        else:
            status_text = error("fail")
        table.add_row(c["name"], c["kind"], status_text, c["note"])
    state.console.print(table)
    state.console.print()

    if hard_failed:
        state.err_console.print(
            error("error:"),
            f"hard requirement(s) missing: {', '.join(hard_failed)}",
        )
        state.err_console.print(
            " ",
            hint("hint:"),
            "install the engine with",
            code("pip install decoy-engine") + ".",
        )
        raise typer.Exit(code=EXIT_RUNTIME)

    state.console.print(success("All checks passed."))


DOCTOR_EPILOG = _DOCTOR_EPILOG
