"""The one reader of a user's pipeline config file.

Eleven commands read the same YAML with their own except lists, and a file that was not UTF-8
reached the crash guard from six of them. Every command now loads through here, so a config
that cannot be read as a mapping gets one code and one text on every surface:

| Step | Failure | Code |
|---|---|---|
| read the bytes | `OSError` | none: re-raised as it is (the environment failed, not the config) |
| strict UTF-8 decode | `UnicodeDecodeError` | `yaml.not_utf8` |
| `yaml.safe_load` | `YAMLError` | `yaml.parse_error` |
| empty document | `None` | `yaml.empty` |
| not a mapping | any non-`dict` | `yaml.not_mapping` |

The file is opened once and the parser sees those bytes, so nothing re-opens the path after the
checks. A `ConfigFileError` is raised after the handler that caught the decode or parse failure
has closed, so it carries no `__context__`, and its text names no byte, line or value of the
file: PyYAML's own text quotes the offending line and a `UnicodeDecodeError` quotes the byte.

Other YAML a command reads (the CI manifest, a policy file, a layout file, text the CLI wrote
itself) is a different kind of input and stays on the allowlist in
`tests/sentry/io_policy/test_config_load_choke_point.py`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from decoy._yaml_errors import sanitize_yaml_error

NOT_UTF8 = "Pipeline YAML is not UTF-8 text."
EMPTY = "Pipeline YAML is empty."


class ConfigFileError(Exception):
    """A config file that cannot be read as a YAML mapping. `code` is public (`yaml.*`), and
    `message` holds no part of the file."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def read_config_text(path: Path) -> str:
    """The file's text: its bytes read once, decoded as strict UTF-8, a leading BOM dropped.

    An `OSError` from the read passes through unchanged."""
    data = path.read_bytes()
    not_utf8 = False
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        not_utf8 = True
    if not_utf8:
        raise ConfigFileError("yaml.not_utf8", NOT_UTF8)
    return text


def parse_config_mapping(text: str) -> dict[str, Any]:
    """The YAML mapping in `text`, or a `ConfigFileError` naming which check failed."""
    parse_failure: str | None = None
    raw: Any = None
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        parse_failure = sanitize_yaml_error(exc)
    if parse_failure is not None:
        raise ConfigFileError("yaml.parse_error", parse_failure)
    if raw is None:
        raise ConfigFileError("yaml.empty", EMPTY)
    if not isinstance(raw, dict):
        raise ConfigFileError(
            "yaml.not_mapping",
            f"Pipeline YAML must be a YAML mapping (object), not {type(raw).__name__}.",
        )
    return raw


def load_config_mapping(path: Path) -> dict[str, Any]:
    """`read_config_text` then `parse_config_mapping`: the one config load."""
    return parse_config_mapping(read_config_text(path))


__all__ = [
    "ConfigFileError",
    "load_config_mapping",
    "parse_config_mapping",
    "read_config_text",
]
