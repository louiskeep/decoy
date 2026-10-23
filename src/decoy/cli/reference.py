"""`decoy list KIND` and `decoy show KIND [NAME]` -- one reference vocabulary.

S3b of the CLI redesign folds the former `strategies`/`providers`/`checksums`/
`validators` sub-apps, the `templates list`/`show` pair, and `schema` into two
verbs over the engine registries:

  decoy list KIND         KIND in {strategies, providers, checksums,
                          validators, templates, disguises}
  decoy show KIND [NAME]  KIND in {strategy, provider, template} (NAME required)
                          plus `show schema` (no NAME, `--output` accepted)

Both verbs are thin dispatch tables onto the existing per-registry readers
(cockpit's `_strategies_list`/`_providers_list`/`_checksums_list`/
`_validators_list`/`_strategies_inspect`/`_providers_inspect`, templates'
`_list`/`_show`, and the `schema` body). The only new reader is `list
disguises`, which enumerates the engine's regulatory Disguise bundles via the
public `decoy_engine.disguises.load_disguises` export.

The dispatched readers' option defaults are `typer.OptionInfo`, not bools, so
the dispatcher always calls them with CONCRETE `json_`/`quiet`/`verbose` values.
"""

from __future__ import annotations

from difflib import get_close_matches
from pathlib import Path
from typing import Callable, Optional

import typer

from decoy.cli.cockpit import (
    _checksums_list,
    _providers_inspect,
    _providers_list,
    _strategies_inspect,
    _strategies_list,
    _validators_list,
)
from decoy.cli.exit_codes import EXIT_USAGE
from decoy.cli.schema import schema as _schema
from decoy.cli.templates import _list as _templates_list
from decoy.cli.templates import _show as _templates_show
from decoy.ui.output import OutputMode, emit_json, setup_output
from decoy.ui.table import make_table
from decoy.ui.theme import accent, code, error, hint

# ---------------------------------------------------------------------------
# list disguises -- new reader over the engine's Disguise bundles (H8)
# ---------------------------------------------------------------------------


def _disguises_list(json_: bool, quiet: bool, verbose: bool) -> None:
    """List every regulatory Disguise bundle shipped by the engine.

    Reads the LIVE bundle catalogue via the public
    `decoy_engine.disguises.load_disguises` export -- the bundle ids
    (`hipaa`, `gdpr`, ...) and field-rule counts are whatever the engine
    ships, never hardcoded here.
    """
    state = setup_output(json_, quiet, verbose)

    # Read the REAL engine bundle catalogue at runtime.
    from decoy_engine.disguises import load_disguises

    bundles = sorted(load_disguises(), key=lambda d: d.id)
    entries = [
        {"id": d.id, "name": d.name, "rules": len(d.field_rules)} for d in bundles
    ]

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": "list disguises",
                "status": "ok",
                "count": len(entries),
                "disguises": entries,
            },
        )
        return

    if state.mode is OutputMode.quiet:
        return

    state.console.print(accent(f"Registered disguise bundles ({len(entries)}):"))
    table = make_table("Id", "Name", "Rules")
    for e in entries:
        table.add_row(e["id"], e["name"], str(e["rules"]))
    state.console.print(table)
    state.console.print()
    state.console.print(
        hint("Tip:"),
        "scaffold a pipeline from one with",
        code("decoy init --preset <id>") + ".",
    )


# ---------------------------------------------------------------------------
# list KIND
# ---------------------------------------------------------------------------

# KIND -> reader. Every reader takes concrete (json_, quiet, verbose) bools.
_LIST_READERS: dict[str, Callable[[bool, bool, bool], None]] = {
    "strategies": _strategies_list,
    "providers": _providers_list,
    "checksums": _checksums_list,
    "validators": _validators_list,
    "templates": _templates_list,
    "disguises": _disguises_list,
}

_LIST_KINDS = tuple(_LIST_READERS)

_LIST_EPILOG = """\
Examples:

  decoy list strategies
    Every registered mask strategy with its class.

  decoy list providers --json
    Every generation provider as JSON.

  decoy list disguises
    The regulatory Disguise bundles (hipaa, gdpr, ...) with rule counts.

Kinds: strategies, providers, checksums, validators, templates, disguises.

See also: decoy show, decoy explain.
"""


def list_(
    kind: str = typer.Argument(
        ...,
        metavar="KIND",
        help="What to list: strategies|providers|checksums|validators|templates|disguises.",
    ),
    json_: bool = typer.Option(
        False, "--json", help="Emit the listing as a JSON envelope instead of a table."
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug-level CLI logs on stderr."
    ),
) -> None:
    """List the contents of one engine registry.

    One verb over the live registries: strategies, providers, checksums,
    validators, templates, and regulatory disguise bundles.
    """
    reader = _LIST_READERS.get(kind)
    if reader is None:
        _reject_kind(
            kind,
            verb="list",
            valid=_LIST_KINDS,
            json_=json_,
            quiet=quiet,
            verbose=verbose,
        )
    # Concrete bools: the readers' own defaults are typer.OptionInfo.
    reader(json_, quiet, verbose)


# ---------------------------------------------------------------------------
# show KIND [NAME]
# ---------------------------------------------------------------------------

# KIND -> inspector for kinds that HAVE a per-item detail view. Each takes
# (name, json_, quiet, verbose).
_SHOW_DETAIL: dict[str, Callable[[str, bool, bool, bool], None]] = {
    "strategy": _strategies_inspect,
    "provider": _providers_inspect,
    "template": _templates_show,
}

# List-only kinds: they appear in `list` but have no detail object (L3).
_SHOW_NO_DETAIL = ("checksum", "validator")

# All KINDs `show` recognises (for the unknown-kind error + cross-suggest).
_SHOW_KINDS = (*_SHOW_DETAIL, *_SHOW_NO_DETAIL, "schema")

# English is irregular (`strategy` -> `strategies`), so map the singular/plural
# pairing explicitly rather than appending/stripping an `s`.
_SINGULAR_TO_PLURAL = {
    "strategy": "strategies",
    "provider": "providers",
    "template": "templates",
    "checksum": "checksums",
    "validator": "validators",
}
_PLURAL_TO_SINGULAR = {v: k for k, v in _SINGULAR_TO_PLURAL.items()}

_SHOW_EPILOG = """\
Examples:

  decoy show strategy fpe
    Details for one mask strategy.

  decoy show provider person_name --json
    One provider's capability matrix as JSON.

  decoy show template hipaa > pipeline.yaml
    Dump one bundled template to stdout.

  decoy show schema -o decoy.schema.json
    Write the PipelineConfig JSON Schema to a file.

Kinds: strategy, provider, template (NAME required); schema (no NAME).

See also: decoy list, decoy validate.
"""


def show(
    kind: str = typer.Argument(
        ...,
        metavar="KIND",
        help="What to show: strategy|provider|template (needs NAME), or schema.",
    ),
    name: Optional[str] = typer.Argument(
        None,
        metavar="[NAME]",
        help="Which item to show. Required for strategy/provider/template; omit for schema.",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="(schema only) Write the schema to this file instead of stdout.",
        show_default=False,
    ),
    json_: bool = typer.Option(
        False, "--json", help="Emit a JSON record instead of human output."
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug-level CLI logs on stderr."
    ),
) -> None:
    """Show detail for one reference item.

    `show strategy|provider|template NAME` gives per-item detail; `show schema`
    prints the PipelineConfig JSON Schema (`--output` writes it to a file).
    Note: `decoy scan show SCAN FIELD` is a different `show` -- it reports a
    field from a saved scan, not a reference item.
    """
    if kind == "schema":
        # schema takes no NAME and uniquely accepts --output. Concrete bools.
        if name is not None:
            state = setup_output(json_, quiet, verbose)
            msg = f"`show schema` takes no NAME (got {name!r}); use `show schema [--output FILE]`."
            if state.mode is OutputMode.json:
                emit_json(state, {"command": "show schema", "status": "error", "error": msg})
            else:
                state.err_console.print(error("error:"), msg)
            raise typer.Exit(code=EXIT_USAGE)
        _schema(output=output, json_=json_, quiet=quiet, verbose=verbose)
        return

    if kind in _SHOW_NO_DETAIL:
        state = setup_output(json_, quiet, verbose)
        msg = (
            f"no detail view for {kind}; detail exists for "
            "strategy/provider/template/schema"
        )
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {"command": "show", "status": "error", "kind": kind, "error": msg},
            )
        elif state.mode is not OutputMode.quiet:
            plural = _SINGULAR_TO_PLURAL[kind]
            state.err_console.print(error("error:"), msg + ".")
            state.err_console.print(
                " ", hint("hint:"), "list them with", code(f"decoy list {plural}") + "."
            )
        raise typer.Exit(code=EXIT_USAGE)

    inspector = _SHOW_DETAIL.get(kind)
    if inspector is None:
        _reject_kind(
            kind,
            verb="show",
            valid=_SHOW_KINDS,
            json_=json_,
            quiet=quiet,
            verbose=verbose,
        )

    if name is None:
        state = setup_output(json_, quiet, verbose)
        msg = f"show {kind} requires a NAME"
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {"command": "show", "status": "error", "kind": kind, "error": msg},
            )
        elif state.mode is not OutputMode.quiet:
            plural = _SINGULAR_TO_PLURAL[kind]
            state.err_console.print(error("error:"), msg + ".")
            state.err_console.print(
                " ",
                hint("hint:"),
                "list the available ones with",
                code(f"decoy list {plural}") + ".",
            )
        raise typer.Exit(code=EXIT_USAGE)

    # Concrete bools: the inspectors' own defaults are typer.OptionInfo.
    inspector(name, json_, quiet, verbose)


# ---------------------------------------------------------------------------
# shared unknown-kind error (with singular/plural cross-suggest)
# ---------------------------------------------------------------------------


def _reject_kind(
    kind: str,
    *,
    verb: str,
    valid: tuple[str, ...],
    json_: bool,
    quiet: bool,
    verbose: bool,
) -> None:
    """Emit a clean EXIT_USAGE naming the valid kinds and raise. Never returns.

    Cross-suggests the right verb for a singular/plural slip: `list strategy`
    hints `list strategies`; `show strategies` hints `show strategy NAME`.
    """
    state = setup_output(json_, quiet, verbose)

    # Singular/plural cross-suggest: `list KIND` wants plurals, `show KIND`
    # wants the singular (and shows a NAME placeholder for detail kinds).
    suggestion: Optional[str] = None
    if verb == "list" and _SINGULAR_TO_PLURAL.get(kind) in valid:
        # A singular typed at `list`, e.g. `list strategy` -> `list strategies`.
        suggestion = f"decoy list {_SINGULAR_TO_PLURAL[kind]}"
    elif verb == "show" and _PLURAL_TO_SINGULAR.get(kind) in valid:
        # A plural typed at `show`, e.g. `show strategies` -> `show strategy NAME`.
        singular = _PLURAL_TO_SINGULAR[kind]
        suggestion = (
            f"decoy show {singular} NAME"
            if singular in _SHOW_DETAIL
            else f"decoy show {singular}"
        )
    else:
        close = get_close_matches(kind, valid, n=1, cutoff=0.6)
        if close:
            singular = close[0]
            if verb == "show" and singular in _SHOW_DETAIL:
                suggestion = f"decoy show {singular} NAME"
            else:
                suggestion = f"decoy {verb} {singular}"

    valid_str = ", ".join(valid)

    if state.mode is OutputMode.json:
        emit_json(
            state,
            {
                "command": verb,
                "status": "error",
                "kind": kind,
                "error": f"unknown kind {kind!r}",
                "valid_kinds": list(valid),
                "did_you_mean": suggestion,
            },
        )
    elif state.mode is not OutputMode.quiet:
        state.err_console.print(error("error:"), f"unknown kind {kind!r}.")
        if suggestion is not None:
            state.err_console.print(
                " ", hint("hint:"), "did you mean", code(suggestion) + "?"
            )
        state.err_console.print(
            " ", hint("hint:"), f"valid kinds for {verb}:", valid_str + "."
        )
    raise typer.Exit(code=EXIT_USAGE)


LIST_EPILOG = _LIST_EPILOG
SHOW_EPILOG = _SHOW_EPILOG

__all__ = ["LIST_EPILOG", "SHOW_EPILOG", "list_", "show"]
