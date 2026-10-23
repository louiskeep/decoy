"""Leak-safe messaging for YAML parse failures.

PyYAML's ``YAMLError`` string form (and ``MarkedYAMLError.get_snippet()``)
embeds the offending source line verbatim. Interpolating ``str(exc)`` into a
user-facing message therefore echoes whatever sat on that line back to the
user -- a password, an API key, raw PII -- into stdout, stderr, and the
``--json`` envelope. Several CLI commands parse a config before doing anything
(`validate`, `validate config`, `compile`, `subset`, `report`), so this leak
had one shape copied across them.

This helper is the one place that turns a parse failure into a message. It
reports only the parse-position coordinates and a fixed classification, never
the exception text or the source snippet.
"""

from __future__ import annotations


def sanitize_yaml_error(exc: Exception) -> str:
    """Return a leak-safe, one-line description of a YAML parse failure.

    Uses the error's line/column mark when PyYAML provides one (its
    ``MarkedYAMLError`` subclasses carry a ``problem_mark``/``context_mark``);
    the only fields read are the integer line and column. ``str(exc)`` and the
    source snippet -- both of which echo the offending line verbatim -- are
    never included. Accepts any exception so a broadened ``except`` cannot
    reintroduce the leak by passing a non-YAML error through.
    """
    mark = getattr(exc, "problem_mark", None) or getattr(exc, "context_mark", None)
    line = getattr(mark, "line", None)
    column = getattr(mark, "column", None)
    if isinstance(line, int) and isinstance(column, int):
        # PyYAML marks are 0-indexed; report 1-indexed to match editors.
        return f"could not parse YAML: invalid syntax at line {line + 1}, column {column + 1}"
    return "could not parse YAML: the file is not valid YAML"


__all__ = ["sanitize_yaml_error"]
