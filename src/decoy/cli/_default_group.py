"""Shared default-command Typer group.

Extracted from `cli/validate.py` (built in S2) under the S3a CLI redesign so
the "a group command that also takes a bare positional" pattern has one home
(reuse-first). `validate` and `scan` both need it: `decoy validate CONFIG` and
`decoy scan SOURCE` each run a hidden default command when the first token is
not one of the group's registered subcommands.

The S2 original hardcoded the hidden command name as `_gate`; this factory
parameterizes it (M1) so each group registers its default under its own name
(`_gate` for validate, `_scan` for scan) instead of a single misleading one.

Mechanism (no new dependency): the vendored-Click `resolve_command` is the one
choke point every non-help dispatch flows through; the subclass overrides it to
fall back to the default command, keeping ALL args (the first token is the
positional for the default command). `list_commands` hides the default from
help, the generated reference, and shell completion while `get_command` can
still resolve it for dispatch.
"""

from __future__ import annotations

from typer.core import TyperGroup


def make_default_group(default_cmd_name: str) -> type[TyperGroup]:
    """Return a `TyperGroup` subclass that dispatches to a hidden default
    command named `default_cmd_name` when the first positional token is NOT a
    registered subcommand (and not an option).

    The group's own `no_args_is_help` still shows help on no args, and real
    subcommands resolve as normal.
    """

    class _DefaultCommandGroup(TyperGroup):
        def resolve_command(self, ctx, args):  # type: ignore[override]
            if args:
                token = args[0]
                if token not in self.commands and not token.startswith("-"):
                    cmd = self.get_command(ctx, default_cmd_name)
                    if cmd is not None:
                        # Keep every arg: `token` is the positional for the default cmd.
                        return default_cmd_name, cmd, args
            return super().resolve_command(ctx, args)

        def list_commands(self, ctx):  # type: ignore[override]
            return [n for n in super().list_commands(ctx) if n != default_cmd_name]

    return _DefaultCommandGroup
