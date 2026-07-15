"""Unit tests for `decoy init <file>` column-aware scaffolding (OSS.4c, 2026-06-02).

Three cells:

  1. ``test_inference_table_covers_canonical_detectors`` -- pin the
     short table to its current contents. The list of detector ids
     under management is a public contract: the project promises a
     default strategy for these specific ids, and the long tail
     falls through to _FALLBACK with a louder REVIEW.

  2. ``test_review_comment_format`` -- the REVIEW comment line shape
     is the operator-facing UX surface; pin "# REVIEW: " prefix +
     wrap width so an indent or rename can't silently degrade
     readability.

  3. ``test_yaml_body_parses_through_pipeline_config`` -- end-to-end
     guard: a hand-built FieldStats list goes through the scaffolder
     and the emitted YAML must pass PipelineConfig.model_validate.
     Catches a regression where the scaffolder emits a key the engine
     refuses.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from decoy.cli._init_inference import (
    _FALLBACK,
    _INFERENCE_TABLE,
    Inference,
    _infer_strategy_for_column,
)
from decoy.cli.init import (
    _build_scaffold_yaml,
    _emit_column_yaml,
    _validate_scaffold,
    _wrap_review_comment,
)


@dataclass
class _FakeMatch:
    """Stand-in for decoy_engine.storm.types.DetectorMatch."""

    detector_id: str
    match_rate: float = 0.9
    confidence_bucket: str = "high"


@dataclass
class _FakeFieldStats:
    """Stand-in for decoy_engine.storm.types.FieldStats."""

    name: str
    detector_matches: list = None
    inferred_type: str = "string"
    is_likely_unique: bool = False

    def __post_init__(self):
        if self.detector_matches is None:
            self.detector_matches = []


def test_inference_table_covers_canonical_detectors():
    """Pin the inference table contents. Detector ids the project
    promises a default for; the long tail falls into _FALLBACK."""
    expected_ids = {
        "email",
        "ssn",
        "us_phone",
        "person_name",
        "iso_date",
        "us_date",
        "us_zip",
        "address_street",
        "address_city",
        "mrn",
        "npi",
        "ndc",
        "icd10",
        "pan",
        "cvv",
        "iban",
        "uuid",
        "ipv4",
    }
    assert set(_INFERENCE_TABLE.keys()) == expected_ids
    # Every entry must carry a non-empty REVIEW reason.
    for det_id, inf in _INFERENCE_TABLE.items():
        assert inf.review, f"empty REVIEW for {det_id!r}"
        if inf.strategy == "faker":
            assert inf.provider, f"faker without provider for {det_id!r}"


def test_fallback_carries_louder_review():
    """The fallback strategy is `redact` with a verbose REVIEW that
    tells the user the scaffolder didn't recognize the column. This
    is the safe default; the user must replace if the column should
    be kept verbatim or carries PII the detectors missed."""
    assert _FALLBACK.strategy == "redact"
    assert "did not flag" in _FALLBACK.review.lower()
    assert _FALLBACK.provider is None


def test_infer_picks_top_detector():
    """When a column has a single confident detector match, the
    scaffolder picks the table entry for that detector."""
    fs = _FakeFieldStats(
        name="contact_email",
        detector_matches=[_FakeMatch(detector_id="email", match_rate=0.95)],
    )
    inf = _infer_strategy_for_column(fs)
    assert inf.strategy == "faker"
    assert inf.provider == "person_email"


def test_infer_falls_back_when_no_detectors():
    """A column with no detector hits gets _FALLBACK (redact + verbose REVIEW)."""
    fs = _FakeFieldStats(name="unknown_col", detector_matches=[])
    inf = _infer_strategy_for_column(fs)
    assert inf.strategy == "redact"
    assert "did not flag" in inf.review.lower()


def test_infer_likely_unique_integer_gets_hash():
    """No detector match + integer + likely unique = hash (treat as FK key)."""
    fs = _FakeFieldStats(
        name="customer_id",
        detector_matches=[],
        inferred_type="integer",
        is_likely_unique=True,
    )
    inf = _infer_strategy_for_column(fs)
    assert inf.strategy == "hash"
    assert "fk key" in inf.review.lower()


def test_infer_ambiguous_marks_review():
    """When two detectors fire at comparable confidence, the REVIEW
    text names both signals so the user knows the scaffolder made a
    coin-flip call."""
    fs = _FakeFieldStats(
        name="weird_col",
        detector_matches=[
            _FakeMatch(detector_id="email", match_rate=0.80),
            _FakeMatch(detector_id="us_phone", match_rate=0.78),
        ],
    )
    inf = _infer_strategy_for_column(fs)
    assert "multiple candidate signals" in inf.review.lower()
    assert "email" in inf.review and "us_phone" in inf.review


def test_review_comment_format():
    """Pin the operator-facing comment shape: `# REVIEW: ` prefix on
    the first wrapped line, plain `# ` on continuations, indent matches
    the surrounding YAML node."""
    body = _wrap_review_comment(
        "STORM detected email addresses. Faker replaces with synthetic emails.",
        indent="      ",
    )
    lines = body.splitlines()
    assert lines[0].startswith("      # REVIEW: ")
    # Continuation lines (if any) start with the indent + plain `# `.
    for cont in lines[1:]:
        assert cont.startswith("      #")


def test_emit_column_yaml_faker_shape():
    """Faker strategy entries carry a `provider:` line."""
    body = _emit_column_yaml(
        "email",
        Inference(strategy="faker", provider="person_email", review="x"),
    )
    assert "- name: email" in body
    assert "strategy: faker" in body
    assert "provider: person_email" in body


def test_emit_column_yaml_date_shift_carries_default_provider_config():
    """date_shift entries get default `provider_config.min_days/max_days`
    (the real keys `_strategies/_date_shift.py` reads) so the rendered
    YAML is runnable without extra user edits. `params` is not a
    ColumnConfig field (extra="forbid"), so it must never appear.

    date_shift also requires a `namespace:` -- execution/_strategies/
    _date_shift.py raises `date_shift_requires_namespace` at runtime with
    none, and there is no compile-time check, so an un-namespaced entry
    would pass `PipelineConfig.model_validate` and only fail at
    `decoy run` (exit 3)."""
    body = _emit_column_yaml(
        "birth_date",
        Inference(strategy="date_shift", review="x"),
    )
    assert "strategy: date_shift" in body
    assert "namespace: birth_date" in body
    assert "provider_config:" in body
    assert "min_days: -365" in body
    assert "max_days: 365" in body
    assert "params:" not in body


def test_emit_column_yaml_truncate_carries_default_provider_config():
    """truncate entries get default `provider_config.length: 3` (HIPAA Safe
    Harbor for ZIP). `keep` is a head/tail direction flag in the engine
    (_strategies/_truncate.py), not a character count, so the scaffold
    must not emit `keep: 3`. truncate does NOT require a namespace
    (unlike hash/fpe/date_shift), so no `namespace:` line is emitted."""
    body = _emit_column_yaml(
        "zip",
        Inference(strategy="truncate", review="x"),
    )
    assert "provider_config:" in body
    assert "length: 3" in body
    assert "params:" not in body
    assert "namespace:" not in body


def test_emit_column_yaml_hash_carries_namespace():
    """hash requires a `namespace:` -- execution/_strategies/_hash.py raises
    `hash_requires_namespace` at runtime with none. No provider_config is
    needed (hash's only optional config key is `truncate`, which the
    scaffold does not set)."""
    body = _emit_column_yaml(
        "customer_id",
        Inference(strategy="hash", review="x"),
    )
    assert "strategy: hash" in body
    assert "namespace: customer_id" in body


def test_emit_column_yaml_faker_and_redact_have_no_namespace():
    """faker and redact do not require a namespace; the scaffold must not
    emit one for them (an unnecessary field is still valid YAML, but the
    REVIEW note explains namespace only where it matters)."""
    faker_body = _emit_column_yaml(
        "email", Inference(strategy="faker", provider="person_email", review="x")
    )
    assert "namespace:" not in faker_body

    redact_body = _emit_column_yaml("cvv", Inference(strategy="redact", review="x"))
    assert "namespace:" not in redact_body


def test_emit_column_yaml_fpe_carries_luhn_config_and_namespace():
    """fpe needs no per-column KEY config -- the Feistel key is derived from
    a fixed label + (job_seed, namespace), not a per-column `key_label`
    (FPE_KEY_LABEL, execution/_strategies/_fpe.py). The old scaffold used to
    emit a phantom `params: {key_label: default}` block; ColumnConfig has no
    `params` field (extra="forbid") so that entry always failed
    PipelineConfig.model_validate.

    fpe DOES require a `namespace:` (execution/_strategies/_fpe.py raises
    `fpe_requires_namespace` at runtime with none) and, for PAN scaffolding
    specifically, a `provider_config: {charset: digits, validate_luhn: true}`
    block -- without it `validate_luhn` defaults False and masked PANs fail
    Luhn (engine `_fpe.py`; check digit only recomputed when enabled,
    `transforms/fpe.py`). This matches the bundled PCI template
    (templates/pci.yaml)."""
    body = _emit_column_yaml(
        "card_number",
        Inference(strategy="fpe", review="x"),
    )
    assert "strategy: fpe" in body
    assert "params:" not in body
    assert "key_label" not in body
    assert "namespace: card_number" in body
    assert "provider_config:" in body
    assert "charset: digits" in body
    assert "validate_luhn: true" in body


def test_yaml_body_parses_through_pipeline_config(tmp_path: Path):
    """End-to-end: build a scaffold body from a hand-built inference
    map and verify it passes PipelineConfig validation.

    This is the canary against schema drift: if a future engine refactor
    renames a key (columns -> mask_rules, etc.) this test fires."""
    input_file = tmp_path / "input.csv"
    input_file.write_text("a,b\n1,2\n", encoding="utf-8")
    output_path = tmp_path / "input.masked.csv"
    inferences = {
        "a": Inference(
            strategy="faker", provider="person_email", review="email"
        ),
        "b": Inference(strategy="redact", review="redact b"),
    }
    body = _build_scaffold_yaml(
        input_path=input_file,
        output_path=output_path,
        column_names=["a", "b"],
        inferences=inferences,
        file_format="csv",
    )
    # Header + REVIEW comments land in the body.
    assert "# REVIEW:" in body
    assert "version: 1" in body
    # PipelineConfig must accept the emitted YAML.
    _validate_scaffold(body)


def test_scaffold_header_cites_oss_4c_provenance(tmp_path: Path):
    """The top of the file tells the user what made it and what to do
    next. Pin the substring so a rewrite of the header copy can't drop
    the operator-facing instruction by accident."""
    input_file = tmp_path / "customers.csv"
    body = _build_scaffold_yaml(
        input_path=input_file,
        output_path=tmp_path / "customers.masked.csv",
        column_names=["email"],
        inferences={
            "email": Inference(
                strategy="faker", provider="person_email", review="email detected"
            )
        },
        file_format="csv",
    )
    assert "decoy init customers.csv" in body
    assert "REVIEW" in body
