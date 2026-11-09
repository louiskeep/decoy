"""The closed vocabulary a CI finding's `rule_id` may carry.

`decoy ci` maps every upstream `.code` (the validation gate) and `.kind` (the evidence
verifier) through an allowlist instead of sanitising the string: a code that is not listed
here becomes `UNKNOWN_CODE`, so no upstream text -- a table name in a templated preflight
check, a future code that interpolates a value -- can reach JSON, SARIF or Markdown. This is
the SARIF `reportingDescriptor.id` contract (a stable rule identifier, not a message) applied
as an allow-list output encoding (OWASP ASVS V5.3: encode against a known-good set).

The engine half is derived from the pinned engine's reason registry on first use (never at
module import, so `decoy ci` can import the engine with its logging silenced), plus the few
literal codes it raises outside the registry; the pydantic-core `ErrorType`, CLI-gate and
evidence-verifier sets are written out. `tests/unit/test_ci_rule_codes.py` re-derives every
set from source and fails when upstream adds a code none of them holds.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from functools import cache

UNKNOWN_CODE = "unknown_code"

# Preflight names that embed the table name (`source.<table>.exists`). The table is user
# data, so only the fixed family token is emitted.
_TEMPLATED = re.compile(
    r"^(?P<family>source|target)\..+\."
    r"(?P<check>type|path|exists|is_file|readable|would_overwrite|parent_missing)$",
    re.DOTALL,
)
_TEMPLATED_CODES = frozenset(
    {
        "source.type",
        "source.path",
        "source.exists",
        "source.is_file",
        "source.readable",
        "target.would_overwrite",
        "target.parent_missing",
    }
)

_CLI_GATE_CODES: frozenset[str] = frozenset(
    {
        "capacity.out_of_core_fk",
        "capacity.plan_uncompilable",
        "capacity.source_unreadable",
        "compile_error",
        "compile.needs_profile",
        "compile_warning",
        "missing_extra",
        "native.companion",
        "native.eligibility",
        "pipeline.validation_error",
        "target_format_suffix_mismatch",
        "target_format_unknown",
        "validation_error",
        "yaml.empty",
        "yaml.not_mapping",
        "yaml.parse_error",
    }
)

_PYDANTIC_ERROR_TYPES: frozenset[str] = frozenset(
    {
        "arguments_type",
        "assertion_error",
        "bool_parsing",
        "bool_type",
        "bytes_invalid_encoding",
        "bytes_too_long",
        "bytes_too_short",
        "bytes_type",
        "callable_type",
        "complex_str_parsing",
        "complex_type",
        "counter_type",
        "dataclass_exact_type",
        "dataclass_type",
        "date_from_datetime_inexact",
        "date_from_datetime_parsing",
        "date_future",
        "date_parsing",
        "date_past",
        "date_type",
        "datetime_from_date_parsing",
        "datetime_future",
        "datetime_object_invalid",
        "datetime_parsing",
        "datetime_past",
        "datetime_type",
        "decimal_max_digits",
        "decimal_max_places",
        "decimal_parsing",
        "decimal_type",
        "decimal_whole_digits",
        "default_factory_not_called",
        "deque_type",
        "dict_type",
        "ellipsis_error",
        "enum",
        "extra_forbidden",
        "finite_number",
        "float_parsing",
        "float_type",
        "fraction_parsing",
        "fraction_type",
        "frozen_dict_type",
        "frozen_field",
        "frozen_instance",
        "frozen_set_type",
        "get_attribute_error",
        "greater_than",
        "greater_than_equal",
        "int_from_float",
        "int_parsing",
        "int_parsing_size",
        "int_type",
        "invalid_key",
        "is_instance_of",
        "is_subclass_of",
        "iterable_type",
        "iteration_error",
        "json_invalid",
        "json_type",
        "less_than",
        "less_than_equal",
        "list_type",
        "literal_error",
        "mapping_type",
        "missing",
        "missing_argument",
        "missing_keyword_only_argument",
        "missing_positional_only_argument",
        "missing_sentinel_error",
        "model_attributes_type",
        "model_type",
        "multiple_argument_values",
        "multiple_of",
        "named_tuple_type",
        "needs_python_object",
        "no_such_attribute",
        "none_required",
        "ordered_dict_type",
        "recursion_loop",
        "set_item_not_hashable",
        "set_type",
        "string_not_ascii",
        "string_pattern_mismatch",
        "string_too_long",
        "string_too_short",
        "string_type",
        "string_unicode",
        "time_delta_parsing",
        "time_delta_type",
        "time_parsing",
        "time_type",
        "timezone_aware",
        "timezone_naive",
        "timezone_offset",
        "too_long",
        "too_short",
        "tuple_type",
        "unexpected_keyword_argument",
        "unexpected_positional_argument",
        "union_tag_invalid",
        "union_tag_not_found",
        "url_parsing",
        "url_scheme",
        "url_syntax_violation",
        "url_too_long",
        "url_type",
        "uuid_parsing",
        "uuid_type",
        "uuid_version",
        "value_error",
    }
)

# A rule_id is a bare token: no space, quote, slash, markup or non-ASCII can ride along.
_SAFE_CODE = re.compile(r"[a-z][a-z0-9_.-]*")


def _codes_from_registry(entries: Iterable[Mapping[str, object]]) -> frozenset[str]:
    """The registry's wire codes, keeping only SARIF-safe tokens (a code that is not one
    stays out and emits as UNKNOWN_CODE; tests/unit/test_ci_rule_codes.py fails on it)."""
    return frozenset(
        code
        for entry in entries
        if isinstance(code := entry.get("code"), str) and _SAFE_CODE.fullmatch(code)
    )


@cache
def _engine_registry_codes() -> frozenset[str]:
    """The engine half, by construction: every identity in the pinned engine's closed,
    versioned reason registry (`decoy_engine.reasons`, F29), tombstones included. Registered
    codes are fixed tokens that carry no values, which is the property this allowlist keeps.

    Derived on first use, not at import: `decoy ci` must first import the engine inside
    `engine_logging_silenced`, or the engine's cwd-relative log file lands in the repository."""
    from decoy_engine import reasons

    return _codes_from_registry(reasons.manifest()["entries"])


# Literal codes the engine emits outside the registry (sources at engine v0.19.0). The test
# holds this set equal to what an AST scan of the installed engine finds minus the registry.
_ENGINE_LITERAL_CODES: frozenset[str] = frozenset(
    {
        "abi-mismatch",  # execution/native/_companion_status.py:346
        "absent",  # execution/native/_companion_status.py:269
        "collision_rate",  # execution/native/_pool_quality.py:442
        "digest",  # declared_casting/_quarantine_local.py:504
        "field_missing",  # execution/_isolated_memwatch.py:44
        "kat-corrupt",  # execution/native/_companion_status.py:147
        "load-error",  # execution/native/_companion_status.py:291
        "magic",  # declared_casting/_quarantine_local.py:439
        "measured",  # execution/_probe.py:461
        "oom_killed",  # execution/_isolated_run.py:520
        "pool_duplicate_rate",  # execution/native/_pool_quality.py:454
        "present-ok",  # execution/native/_companion_status.py:384
        "process_exited",  # execution/_isolated_memwatch.py:44
        "read_error",  # execution/_isolated_memwatch.py:44
        "stopped",  # execution/_isolated_memwatch.py:44
        "thread_start_failed",  # execution/_isolated_memwatch.py:44
        "type",  # config/_declared_casting.py:55
        "unreachable",  # secret_providers/_preflight.py:216
    }
)

EVIDENCE_KINDS: frozenset[str] = frozenset(
    {
        "input_fingerprint_changed",
        "input_missing",
        "manifest_hash_mismatch",
        "output_fingerprint_changed",
        "output_missing",
        "pipeline_fingerprint_changed",
        "pipeline_missing",
    }
)


@cache
def validation_codes() -> frozenset[str]:
    """Every code a validation finding's rule_id may carry."""
    return (
        _CLI_GATE_CODES
        | _PYDANTIC_ERROR_TYPES
        | _engine_registry_codes()
        | _ENGINE_LITERAL_CODES
        | _TEMPLATED_CODES
    )


def rule_code(code: object, allowed: frozenset[str]) -> str:
    """`code` itself when allowlisted, its family token when templated, else UNKNOWN_CODE."""
    if not isinstance(code, str):
        return UNKNOWN_CODE
    if code in allowed:
        return code
    match = _TEMPLATED.match(code)
    if match is not None:
        family = f"{match['family']}.{match['check']}"
        if family in allowed:
            return family
    return UNKNOWN_CODE


__all__ = ["EVIDENCE_KINDS", "UNKNOWN_CODE", "rule_code", "validation_codes"]
