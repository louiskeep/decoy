"""The value-free contract for `decoy pre-scan` and `decoy post-scan`: closed types, no I/O.

What may cross to a surface is decided by type, not by where a value came from:

  * `SafeStr` is the only string a `Projection` accepts. It can be minted only by
    the policy constructors below (closed vocabulary, policed schema name, opaque
    label, ISO timestamp, allowlisted type name, static literal). A plain `str`
    -- including any string derived from a `SafeStr` by slicing, formatting or
    concatenation, which Python returns as plain `str` -- is refused by `mint`.
  * `Projection` is minted against a closed schema registry: an unknown schema id
    or a plain-`str` key outside that schema's declared keys is refused.
  * Errors are closed reason keys (`REASONS`), positions are a typed `Location`,
    and exception/warning classes are named only through `safe_cls_name`, which
    allowlists statically defined classes from known modules.

Contract stated honestly: no cell values, file paths, table names or free-text
diagnostics reach a surface. Policed schema identifiers (column names of at most
64 characters matching `[A-Za-z0-9_][A-Za-z0-9_ .-]*`) are schema and ARE output.

This module performs no I/O; process containment and every write live in
`decoy.cli._boundary`. Kept dependency-free so it can be lifted into the engine
as the shared contract.

Pattern: parse-don't-validate (Alexis King, 2019) via a phantom-typed string, the
platform's typed `fidelity-report/v1` projection (decoy-platform
`api/jobs/fidelity_projection.py`), and RFC 9457-style closed problem codes
(stable type code, fixed title, no echoed input).
"""

from __future__ import annotations

import math
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any, LiteralString

from decoy.cli.exit_codes import EXIT_RUNTIME, EXIT_USAGE

_MINT = object()

MAX_IDENTIFIER_LENGTH = 64
UNRECOGNIZED = "unrecognized"
_IDENTIFIER = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_ .\-]*")
_TYPE_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")
_KEY_IDENT = re.compile(r"[a-z_][a-z0-9_]{0,63}")
# Exact module or a dotted child of it. Static library/stdlib classes carry no data in their names.
_TYPE_MODULES = ("builtins", "decoy", "decoy_engine", "pydantic", "pydantic_core", "yaml", "json")


# ---------------------------------------------------------------------------
# SafeStr and its only constructors.
# ---------------------------------------------------------------------------


class SafeStr(str):
    """A string proven to come from a closed policy. Mint only via this module."""

    __slots__ = ()

    def __new__(cls, value: str, token: object = None) -> SafeStr:
        if token is not _MINT or type(value) is not str:
            raise TypeError("SafeStr is minted only by the value-free policy constructors")
        return super().__new__(cls, value)


def _mint_str(value: str) -> SafeStr:
    return SafeStr(str(value), _MINT)


SAFE_UNRECOGNIZED = _mint_str(UNRECOGNIZED)


def literal(value: LiteralString) -> SafeStr:
    """A compile-time constant (notes, fixed codes). The sentry forbids data here."""
    return _mint_str(value)


def vocab(value: Any, allowed: frozenset[str]) -> SafeStr:
    """An exact member of a closed set; anything else becomes `unrecognized`."""
    return _mint_str(value) if type(value) is str and value in allowed else SAFE_UNRECOGNIZED


def vocab_or_none(value: Any, allowed: frozenset[str]) -> SafeStr | None:
    return _mint_str(value) if type(value) is str and value in allowed else None


def is_clean_name(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) <= MAX_IDENTIFIER_LENGTH
        and _IDENTIFIER.fullmatch(value) is not None
    )


def clean_name(value: Any) -> SafeStr | None:
    """A policed schema identifier, or None when it fails the clean-name rule."""
    return _mint_str(str(value)) if is_clean_name(value) else None


OPAQUE_PREFIXES = frozenset({"field", "redacted-name", "table"})


def opaque_label(prefix: str, n: int) -> SafeStr:
    """`field-N` / `redacted-name-N` / `table-N`: a closed prefix and an ordinal."""
    if prefix not in OPAQUE_PREFIXES or type(n) is not int or n < 1:
        raise ValueError("opaque labels take a closed prefix and a positive ordinal")
    return _mint_str(f"{prefix}-{n}")


def iso_timestamp(value: Any) -> SafeStr | None:
    if type(value) is not str or len(value) > 64:
        return None
    try:
        return _mint_str(datetime.fromisoformat(value).isoformat())
    except ValueError:
        return None


JOIN_SEPARATORS = frozenset({"+"})


def join_safe(sep: str, parts: list[SafeStr | None]) -> SafeStr:
    """Join already-minted parts with a closed separator (a joint `a+b` name)."""
    if sep not in JOIN_SEPARATORS:
        raise ValueError("unknown separator")
    return _mint_str(sep.join(p if type(p) is SafeStr else UNRECOGNIZED for p in parts))


# ---------------------------------------------------------------------------
# Exception and warning type names: static classes from allowlisted modules only.
# ---------------------------------------------------------------------------


def safe_cls_name(cls: Any, fallback: str = "Exception") -> SafeStr:
    """The class name when it is statically defined in an allowlisted module, else `fallback`.

    A dynamically built class (`type(f"Err_{secret}", ...)`) is not bound under its
    name in its module, so even one created inside an allowlisted package collapses.
    """
    fallback_safe = _mint_str("Warning" if fallback == "Warning" else "Exception")
    if not isinstance(cls, type):
        return fallback_safe
    mod = getattr(cls, "__module__", None)
    name = getattr(cls, "__qualname__", None)
    if type(mod) is not str or type(name) is not str or not _TYPE_IDENT.fullmatch(name):
        return fallback_safe
    if not any(mod == p or mod.startswith(p + ".") for p in _TYPE_MODULES):
        return fallback_safe
    module = sys.modules.get(mod)
    if module is None or module.__dict__.get(name) is not cls:
        return fallback_safe
    return _mint_str(name)


def exc_label(exc: BaseException) -> SafeStr:
    return safe_cls_name(type(exc), "Exception")


def known_type_name(value: Any) -> SafeStr | None:
    """An engine-reported exception type NAME (a string): kept only when it names an
    allowlisted static exception class, else the generic `Exception`."""
    if value is None:
        return None
    if type(value) is not str or not _TYPE_IDENT.fullmatch(value):
        return _mint_str("Exception")
    stack: list[type] = [BaseException]
    seen: set[type] = set()
    while stack:
        cls = stack.pop()
        if cls in seen:
            continue
        seen.add(cls)
        if cls.__name__ == value and safe_cls_name(cls) == value:
            return _mint_str(value)
        stack.extend(cls.__subclasses__())
    return _mint_str("Exception")


# ---------------------------------------------------------------------------
# Projections: closed schemas, SafeStr-only strings.
# ---------------------------------------------------------------------------

_FIELD_RECORD = {
    "name", "dtype", "null_rate", "distinct_count", "pii_score", "pii_bucket",
    "pii_candidate", "detector_hits",
}  # fmt: skip
_DIFF_ROW = {
    "name",
    "pii_score",
    "pii_bucket",
    "old_score",
    "new_score",
    "old_bucket",
    "new_bucket",
}
_DIFF_GROUPS = {
    "added", "removed", "pii_increased", "pii_decreased", "qi_groups_added", "qi_groups_removed",
}  # fmt: skip
_INTEGRITY = {
    "source_schema_version", "generated_at", "pass_count", "warning_count", "fail_count",
    "error_count", "pass_failed_with", "buckets", "residual_pii", "fk_preservation",
    "policy_validation", "note", "findings", "severities",
    "table", "column", "detector", "severity", "match_rate", "sample_match_count",
    "configured_strategy", "source_identity_rate", "source_compared",
    "parent_table", "parent_column", "child_table", "child_column", "orphan_count",
    "total_child_rows", "orphan_rate", "namespace",
    "strategy", "source_distinct", "output_distinct", "bytes_identical",
}  # fmt: skip
_FIDELITY = {
    "source_schema_version", "generated_at", "grade", "overall_score", "marginal_score",
    "pairwise_score", "shape_score", "diagnostic_passed", "source_row_count",
    "output_row_count", "sampled", "sample_size", "columns", "pairs", "warnings",
    "omissions", "policy", "note",
    "name", "score", "comparable", "method", "shape_method",
    "source", "code", "column", "kind", "severity", "threshold", "metric", "reason",
    "schema_version", "verdict", "mode", "violations", "check", "expected", "actual",
}  # fmt: skip

_PROFILE = {
    "row_count", "field_count", "sample_strategy", "pii_candidate_count", "pii_note",
    "reid_risk_score", "quasi_identifier_groups", "saved", "fields", *_FIELD_RECORD,
}  # fmt: skip
_FIELD_LIST = {"matched", "total", "fields", "name", "pii_score", "pii_bucket", "quasi_identifier"}
_FIELD_DETAIL = {
    "field", "pii_bucket", "quasi_identifier_groups", "sentinel_count", "values_withheld",
    *_FIELD_RECORD,
}  # fmt: skip
_DIFF = {"summary", "changes", "drift", "reid_risk_delta", *_DIFF_GROUPS, *_DIFF_ROW}

SCHEMAS: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "pre-scan-profile/v1": frozenset(_PROFILE),
        "pre-scan-fields/v1": frozenset(_FIELD_LIST),
        "pre-scan-field/v1": frozenset(_FIELD_DETAIL),
        "pre-scan-diff/v1": frozenset(_DIFF),
        "integrity-report/v1": frozenset(_INTEGRITY),
        "fidelity-report/v1": frozenset(_FIDELITY),
    }
)

SafeScalar = SafeStr | int | float | bool | None


@dataclass(frozen=True)
class Projection:
    """A value-free payload. Construct only with `mint`."""

    schema: str
    body: Mapping[str, Any]
    token: object = None

    def __post_init__(self) -> None:
        if self.token is not _MINT:
            raise TypeError("Projection is minted by decoy.cli._value_free.mint only")
        keys = SCHEMAS.get(self.schema)
        if keys is None:
            raise TypeError("unknown projection schema")
        check_safe_payload(self.body, keys)

    def json(self) -> dict[str, Any]:
        return {"schema_version": self.schema, **self.body}


def mint(schema: str, body: dict[str, Any]) -> Projection:
    return Projection(schema, MappingProxyType(body), _MINT)


def is_minted(value: Any) -> bool:
    return isinstance(value, Projection) and value.token is _MINT


def check_safe_payload(value: Any, keys: frozenset[str]) -> None:
    """Refuse a plain `str` anywhere, and any key outside the schema or the key grammar."""
    if value is None or type(value) in (bool, int):
        return
    if type(value) is SafeStr:
        return
    if isinstance(value, str):
        raise TypeError("a plain str cannot cross the value-free boundary; mint a SafeStr")
    if type(value) is float:
        if not math.isfinite(value):
            raise TypeError("non-finite number in projection")
        return
    if isinstance(value, Mapping):
        for k, v in value.items():
            if type(k) is str and k not in keys:
                raise TypeError("projection key is not in the schema")
            if type(k) not in (str, SafeStr) or not _KEY_IDENT.fullmatch(k):
                raise TypeError("projection keys must be schema identifiers")
            check_safe_payload(v, keys)
        return
    if type(value) in (list, tuple):
        for v in value:
            check_safe_payload(v, keys)
        return
    raise TypeError(f"{safe_cls_name(type(value))} cannot cross the value-free boundary")


# ---------------------------------------------------------------------------
# Closed reason table: the only error text these commands can print.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Reason:
    code: str
    message: str
    hint: str | None = None
    exit_code: int = EXIT_USAGE


_NO_TRACE = "no traceback is printed: diagnostics can carry row data."
_SCAN_HINT = "pass the JSON file produced by decoy pre-scan --output scan.json"
_LAYOUT_HINT = "each column needs a string 'name' and integer 'start' (0-indexed) and 'width'."

REASONS: Mapping[str, Reason] = MappingProxyType(
    {
        # pre-scan
        "output_stream_conflict": Reason(
            "usage_error",
            "--output - cannot be combined with --json or --quiet.",
            "use --json for the envelope, or --output - alone for the projection.",
        ),
        "layout_required": Reason(
            "usage_error",
            "fixed-width input requires --layout: column boundaries are ambiguous "
            "without an explicit layout spec.",
            "provide a layout file: decoy pre-scan SOURCE --layout layout.yaml",
        ),
        "layout_not_found": Reason("usage_error", "the --layout file was not found."),
        "layout_invalid": Reason("layout_invalid", "the --layout file is invalid.", _LAYOUT_HINT),
        "scan_failed": Reason("scan_failed", "scan failed.", _NO_TRACE, EXIT_RUNTIME),
        "scan_is_raw_data": Reason(
            "scan_unreadable",
            "the input looks like raw data, not a pre-scan profile JSON.",
            "scan it first: decoy pre-scan SOURCE --output scan.json",
        ),
        "scan_not_found": Reason(
            "scan_unreadable", "could not open the scan file: file not found.", _SCAN_HINT
        ),
        "scan_not_json": Reason(
            "scan_unreadable", "could not parse the scan file as JSON.", _SCAN_HINT
        ),
        "scan_unreadable": Reason("scan_unreadable", "could not read the scan file.", _SCAN_HINT),
        "field_not_found": Reason(
            "usage_error",
            "the requested field is not in the scan.",
            "list all fields with: decoy pre-scan fields SCAN_FILE",
        ),
        "diff_two_stdin": Reason(
            "usage_error",
            "only one of OLD or NEW can be `-` (stdin).",
            "pipe one scan, pass the other as a path.",
        ),
        # post-scan
        "joint_format": Reason("usage_error", "--joint expects 'colA,colB'."),
        "grade_and_score": Reason(
            "usage_error", "specify only one of --min-grade / --min-score, not both."
        ),
        "grade_invalid": Reason("usage_error", "--min-grade must be one of A, B, C, D."),
        "mode_invalid": Reason("usage_error", "--mode must be one of report, warn, fail."),
        "config_invalid": Reason("config_invalid", "could not parse --config."),
        "config_not_yaml": Reason("config_invalid", "could not parse YAML in --config."),
        "policy_not_yaml": Reason("config_invalid", "could not parse YAML in --policy."),
        "policy_invalid": Reason("config_invalid", "could not parse --policy."),
        "policy_not_mapping": Reason("config_invalid", "--policy must be a YAML/JSON mapping."),
        "source_unreadable": Reason("input_unreadable", "could not read the source file."),
        "output_unreadable": Reason("input_unreadable", "could not read the output file."),
        "input_not_found": Reason("input_unreadable", "could not open an input file (not found)."),
        "fidelity_failed": Reason(
            "check_failed", "fidelity measurement failed.", _NO_TRACE, EXIT_RUNTIME
        ),
        "integrity_failed": Reason(
            "check_failed", "integrity check failed.", _NO_TRACE, EXIT_RUNTIME
        ),
        # shared
        "verbose_and_quiet": Reason(
            "usage_error",
            "--verbose and --quiet are mutually exclusive.",
            "pick one -- `-v` for diagnostics, `-q` to silence stdout.",
        ),
        "json_and_quiet": Reason(
            "usage_error",
            "--json and --quiet are mutually exclusive.",
            "use `--json` for structured stdout, `--quiet` for none.",
        ),
        "report_write_failed": Reason(
            "write_failed", "could not write the report file.", None, EXIT_RUNTIME
        ),
        "interrupted": Reason("interrupted", "interrupted.", None, 130),
        "unexpected": Reason("internal_error", "unexpected failure.", _NO_TRACE, EXIT_RUNTIME),
    }
)

NOTICES: Mapping[str, str] = MappingProxyType(
    {
        "source_mismatch": (
            "--source does not match the pipeline's declared input path; proceeding "
            "with --source as ground truth (suppress with --allow-source-mismatch)."
        ),
    }
)

# Labels a Surface may carry; the envelope `command` field is one of these.
COMMANDS = frozenset(
    {
        "pre-scan",
        "pre-scan fields",
        "pre-scan show",
        "pre-scan diff",
        "post-scan",
        "post-scan integrity",
        "post-scan fidelity",
    }
)
ENVELOPE_STATUSES = frozenset({"ok", "findings", "pass", "warn", "fail", "error"})


class StageId(str, Enum):
    """The closed set of progress stage labels."""

    LOAD_SOURCE = "Load source"
    PROFILE_COLUMNS = "Profile columns"
    SUMMARIZE = "Summarize"


# ---------------------------------------------------------------------------
# Typed locations: positions and closed rule codes, never the offending value.
# ---------------------------------------------------------------------------

LAYOUT_KEYS = frozenset({"name", "start", "width"})
LAYOUT_RULES: Mapping[str, str] = MappingProxyType(
    {
        "not_parseable": "the file is not valid YAML or JSON",
        "not_mapping": "the file must be a mapping with a 'columns' key",
        "columns_not_list": "'columns' must be a list of column mappings",
        "entry_not_mapping": "the entry must be a mapping",
        "name_missing": "'name' is missing or empty",
        "value_missing": "a required key is missing",
        "not_integer": "the value must be an integer",
        "start_negative": "'start' must be >= 0",
        "width_not_positive": "'width' must be > 0",
    }
)


@dataclass(frozen=True)
class Location:
    """Where a parse problem is. Every field is an ordinal or a closed code."""

    kind: str  # "yaml" | "layout"
    line: int | None = None
    column: int | None = None
    index: int | None = None
    key: str | None = None
    rule: str | None = None

    def as_json(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}

    def text(self) -> str:
        if self.kind == "yaml" and self.line is not None:
            return f"invalid syntax at line {self.line}, column {self.column}"
        parts = []
        if self.index is not None:
            parts.append(f"layout column {self.index}")
        if self.key is not None:
            parts.append(f"key '{self.key}'")
        rule = LAYOUT_RULES.get(self.rule or "", "invalid entry")
        return (", ".join(parts) + ": " if parts else "") + rule


def yaml_location(exc: BaseException) -> Location | None:
    """Line/column of a PyYAML mark (1-indexed); the snippet and message are dropped."""
    mark = getattr(exc, "problem_mark", None) or getattr(exc, "context_mark", None)
    line, column = getattr(mark, "line", None), getattr(mark, "column", None)
    if type(line) is int and type(column) is int:
        return Location("yaml", line=line + 1, column=column + 1)
    return None


class LayoutError(ValueError):
    """A layout problem described by entry index + closed key/rule codes only."""

    def __init__(self, rule: str, *, index: int | None = None, key: str | None = None) -> None:
        if rule not in LAYOUT_RULES:
            raise ValueError("unknown layout rule")
        if key is not None and key not in LAYOUT_KEYS:
            raise ValueError("unknown layout key")
        if index is not None and (type(index) is not int or index < 0):
            raise ValueError("layout index must be a non-negative ordinal")
        super().__init__(rule)
        self.location = Location("layout", index=index, key=key, rule=rule)
