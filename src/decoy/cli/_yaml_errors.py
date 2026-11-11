"""Leak-safe messaging for YAML parse failures.

PyYAML's ``YAMLError`` string form (and ``MarkedYAMLError.get_snippet()``) embeds the offending
source line verbatim, so interpolating ``str(exc)`` into a user-facing message echoes whatever sat
on that line (a password, an API key, raw PII) into stdout, stderr and the ``--json`` envelope.

The text now lives in the engine (``decoy_engine.safe_output.yaml_error_text``), the one copy the
engine's own config loader uses. This name stays for the commands that import it.
"""

from __future__ import annotations

from decoy_engine.safe_output import yaml_error_text as sanitize_yaml_error

__all__ = ["sanitize_yaml_error"]
