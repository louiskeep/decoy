"""`decoy init` -- interactive scaffolder for a starter pipeline YAML.

The only place wizards belong (CLI_UX_GUIDE.md section 13). Walks the user
through a couple of prompts and writes a starter `pipeline.yaml` they can
iterate on. The body of every preset comes from `decoy.templates`, so
`decoy init --preset hipaa` and `decoy templates show hipaa` produce the
same YAML up to input/output path edits.
"""

from __future__ import annotations

from pathlib import Path

import typer

from decoy.cli.completers import init_presets
from decoy.templates import get_template, template_names as _template_names
from decoy.ui.output import OutputMode, emit_json, setup_output
from decoy.ui.theme import accent, code, error, hint, success


_INIT_EPILOG = """\
Examples:

  decoy init
    Interactive Q&A; writes pipeline.yaml in the current directory.

  decoy init --preset hipaa --out hipaa_pipeline.yaml
    Skip the wizard; scaffold from the HIPAA template.

  decoy init --yes
    Skip confirmation when overwriting an existing file.

See also: decoy validate, decoy run, decoy templates list.
"""


# Templates used by the wizard. Anything in `decoy.templates` is fair game --
# but only flat masking templates make sense to path-edit. `generate` and
# `graph` need different question sets, so they're routed through unchanged.
_PATHED_PRESETS: tuple[str, ...] = ("minimal", "hipaa", "pci", "gdpr")


def _render(preset: str, input_path: str | None, output_path: str | None) -> str:
    """Build the YAML body for a preset, optionally rewriting input/output paths.

    For flat masking presets (minimal/hipaa/pci/gdpr), substitute the wizard's
    chosen paths into the bundled template. For generate/graph, return the
    template as-is -- their YAML shapes don't have a single input.path key.
    """
    template = get_template(preset)
    if template is None:
        raise ValueError(f"unknown preset: {preset!r}")
    body = template.body
    if preset in _PATHED_PRESETS and input_path and output_path:
        # Replace only the first input.path / output.path string; the bundled
        # templates put each on a single line with single quotes.
        body = _replace_yaml_path(body, "input", input_path)
        body = _replace_yaml_path(body, "output", output_path)
    return body


def _replace_yaml_path(body: str, key: str, new_path: str) -> str:
    """Surgical edit: rewrite the first `path: '...'` under `key:`.

    Avoids pulling in a YAML round-tripper just to update two paths; the
    bundled templates have a known, narrow shape that this regex matches.
    """
    import re

    pattern = re.compile(
        rf"(^{key}:\s*\n(?:[^\S\n]+[^\n]*\n)*?[^\S\n]+path:\s*)'[^']*'",
        re.MULTILINE,
    )
    return pattern.sub(rf"\1'{new_path}'", body, count=1)


def _rule_count(body: str) -> int:
    """Cheap count of `- column:` lines so the JSON envelope can report it."""
    return sum(1 for line in body.splitlines() if line.strip().startswith("- column:"))


def _init(
    out: Path = typer.Option(
        Path("pipeline.yaml"),
        "--out",
        help="Where to write the pipeline YAML.",
    ),
    preset: str = typer.Option(
        None,
        "--preset",
        help="Skip the preset prompt and use this template directly.",
        autocompletion=init_presets,
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip overwrite confirmation.",
    ),
    json_: bool = typer.Option(
        False, "--json", help="Skip the wizard; emit a JSON record of what was written."
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress stdout. Errors still go to stderr."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable debug-level CLI logs on stderr."
    ),
) -> None:
    """Scaffold a starter pipeline YAML through a short Q&A.

    Use this on a fresh project to get a working pipeline you can run end to
    end, then edit the rules and paths to match your data. The wizard is the
    only interactive prompt in the CLI -- every other command is one-shot.
    """
    state = setup_output(json_, quiet, verbose)

    # Validate --preset early so the error path is consistent across modes.
    if preset is not None and preset not in _template_names():
        from difflib import get_close_matches

        guess = get_close_matches(preset, _template_names(), n=1, cutoff=0.5)
        if state.mode is OutputMode.json:
            emit_json(
                state,
                {
                    "command": "init",
                    "status": "error",
                    "preset": preset,
                    "error": f"unknown preset {preset!r}",
                    "did_you_mean": guess[0] if guess else None,
                },
            )
        elif state.mode is not OutputMode.quiet:
            state.err_console.print(error("error:"), f"unknown preset {preset!r}.")
            if guess:
                state.err_console.print(
                    " ", hint("hint:"), "did you mean", code(guess[0]) + "?"
                )
            else:
                state.err_console.print(
                    " ",
                    hint("hint:"),
                    "list every preset with",
                    code("decoy templates list") + ".",
                )
        raise typer.Exit(code=1)

    if out.exists() and not yes:
        if state.mode is not OutputMode.default:
            state.err_console.print(error("error:"), f"{out} already exists.")
            state.err_console.print(" ", hint("hint:"), "rerun with --yes to overwrite.")
            raise typer.Exit(code=1)
        size = out.stat().st_size
        state.console.print(
            f"This will overwrite {out} ({size} bytes). Continue?",
        )
        if not typer.confirm("Overwrite?", default=False):
            state.console.print(hint("aborted."))
            raise typer.Exit(code=1)

    if state.mode is OutputMode.json:
        # Non-interactive: produce a scaffold with the chosen (or default) preset.
        chosen = preset or "minimal"
        rendered = _render(chosen, "data/input.csv", "data/masked.csv")
        out.write_text(rendered, encoding="utf-8")
        emit_json(
            state,
            {
                "command": "init",
                "status": "ok",
                "out": str(out),
                "preset": chosen,
                "rule_count": _rule_count(rendered),
            },
        )
        return

    if state.mode is OutputMode.quiet:
        chosen = preset or "minimal"
        rendered = _render(chosen, "data/input.csv", "data/masked.csv")
        out.write_text(rendered, encoding="utf-8")
        return

    # Interactive Q&A.
    state.console.print(accent("decoy init"), "-- starter pipeline scaffold")
    state.console.print(hint("press Enter to accept the default in [brackets]."))
    state.console.print()

    if preset is None:
        choices = " | ".join(_template_names())
        chosen = typer.prompt(
            f"Preset ({choices})",
            default="minimal",
        ).strip().lower()
        while chosen not in _template_names():
            state.console.print(error("error:"), f"unknown preset {chosen!r}.")
            state.console.print(
                " ", hint("hint:"), f"pick one of: {', '.join(_template_names())}."
            )
            chosen = typer.prompt("Preset", default="minimal").strip().lower()
    else:
        chosen = preset

    if chosen in _PATHED_PRESETS:
        input_path = typer.prompt("Input CSV path", default="data/input.csv")
        output_path = typer.prompt("Output CSV path", default="data/masked.csv")
        rendered = _render(chosen, input_path, output_path)
    else:
        # generate / graph: their YAMLs use different keys; ship as-is.
        rendered = _render(chosen, None, None)

    out.write_text(rendered, encoding="utf-8")

    state.console.print()
    state.console.print(success("OK"), "wrote", code(str(out)), "(preset:", code(chosen) + ")")
    state.console.print(hint("Next:"), code(f"decoy validate {out}"))


_init.__doc__ = _init.__doc__

INIT_EPILOG = _INIT_EPILOG


def init_command():  # exported for __main__
    return _init
