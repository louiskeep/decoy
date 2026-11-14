"""The hand-emitted YAML text `decoy init` writes: scalars, REVIEW comments, one column block.

Split from `cli/init.py`, which re-imports these names (its tests reach them there).
"""

from __future__ import annotations

import json as _json

from decoy.cli._init_inference import Inference


def _yaml_scalar(value: object) -> str:
    """A dialect value as a YAML scalar: bools as true/false, text as a JSON-quoted string."""
    return str(value).lower() if isinstance(value, bool) else _json.dumps(value)


def _yaml_quote(value: str) -> str:
    """Quote a string for the hand-emitted YAML.

    Single-quoted style matches the bundled templates. Single quotes
    inside the value are escaped by doubling, per the YAML 1.1 spec
    section 5.3.2 (single-quoted scalars).
    """
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def _wrap_review_comment(review: str, indent: str) -> str:
    """Wrap a REVIEW comment to ~80 columns and prefix `# REVIEW: ` to the
    first line, plain `# ` to continuations.

    Indent is the leading whitespace of the surrounding YAML node so
    the comment lines up with the entry it annotates.
    """
    import textwrap

    width = max(40, 80 - len(indent) - len("# REVIEW: "))
    lines = textwrap.wrap(review, width=width) or [""]
    out = [f"{indent}# REVIEW: {lines[0]}"]
    for cont in lines[1:]:
        out.append(f"{indent}#   {cont}")
    return "\n".join(out)


# Strategies that raise `<strategy>_requires_namespace` at RUNTIME
# (execution/_strategies/*.py) when `ColumnConfig.namespace` is None.
# `ColumnConfig.namespace` defaults to None and there is no compile-time
# check, so a scaffold omitting `namespace:` for one of these passes
# `decoy validate config` / `PipelineConfig.model_validate` cleanly and
# then fails `decoy run` with exit 3. hash/fpe/date_shift are the
# strategies this scaffolder currently emits; shuffle/categorical/
# bucket_perturb/code_set are included for completeness/future-proofing
# even though today's `_INFERENCE_TABLE` never picks them.
_NAMESPACE_REQUIRED_STRATEGIES: frozenset[str] = frozenset(
    {"hash", "fpe", "date_shift", "shuffle", "categorical", "bucket_perturb", "code_set"}
)


def _emit_column_yaml(name: str, inference: Inference, indent: str = "      ") -> str:
    """Emit one column block: REVIEW comment + `- name: ...` body.

    The shape matches engine `ColumnConfig` (decoy_engine.config._tables):
    columns under tables[].columns carry name + strategy + (provider for
    faker) + namespace (required for hash/fpe/date_shift/shuffle/
    categorical/bucket_perturb/code_set -- see
    `_NAMESPACE_REQUIRED_STRATEGIES`) + (provider_config for date_shift /
    truncate / fpe -- ColumnConfig has no `params` field; extra="forbid"
    rejects one). date_shift reads provider_config['min_days'] /
    ['max_days'] (_strategies/_date_shift.py); truncate reads
    provider_config['length'] (_strategies/_truncate.py -- 'keep' there is
    a 'head'/'tail' direction flag, not a character count); fpe reads
    provider_config['charset'] / ['validate_luhn']
    (_strategies/_fpe.py) -- the scaffold emits charset: digits +
    validate_luhn: true so masked PANs stay Luhn-valid, matching the
    bundled PCI template (templates/pci.yaml).

    Namespace value: the column name (`namespace: <name>`), verified to
    validate and run. REVIEW: columns that SHARE a namespace mask
    consistently (same source value -> same masked value across those
    columns); the per-column default here gives every column its own
    namespace, which is safe but does not give cross-column coherence
    (e.g. two columns that both hold the same customer id). Edit the
    namespace value by hand if you need that.
    """
    lines = [_wrap_review_comment(inference.review, indent)]
    lines.append(f"{indent}- name: {name}")
    body_indent = indent + "  "
    lines.append(f"{body_indent}strategy: {inference.strategy}")
    if inference.strategy == "faker" and inference.provider:
        lines.append(f"{body_indent}provider: {inference.provider}")
    if inference.strategy in _NAMESPACE_REQUIRED_STRATEGIES:
        lines.append(f"{body_indent}namespace: {name}")
    if inference.strategy == "date_shift":
        lines.append(f"{body_indent}provider_config:")
        lines.append(f"{body_indent}  min_days: -365")
        lines.append(f"{body_indent}  max_days: 365")
    elif inference.strategy == "truncate":
        lines.append(f"{body_indent}provider_config:")
        lines.append(f"{body_indent}  length: 3")
    elif inference.strategy == "fpe":
        lines.append(f"{body_indent}provider_config:")
        lines.append(f"{body_indent}  charset: digits")
        lines.append(f"{body_indent}  validate_luhn: true")
    if inference.deterministic:
        lines.append(f"{body_indent}deterministic: true")
    return "\n".join(lines)
