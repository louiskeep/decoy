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
    Inference,
    _FALLBACK,
    _INFERENCE_TABLE,
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


def test_emit_column_yaml_date_shift_carries_default_params():
    """date_shift entries get default `range_days: 30` so the rendered
    YAML is runnable without extra user edits."""
    body = _emit_column_yaml(
        "birth_date",
        Inference(strategy="date_shift", review="x"),
    )
    assert "strategy: date_shift" in body
    assert "range_days: 30" in body


def test_emit_column_yaml_truncate_carries_default_params():
    """truncate entries get default `keep: 3` (HIPAA Safe Harbor for ZIP)."""
    body = _emit_column_yaml(
        "zip",
        Inference(strategy="truncate", review="x"),
    )
    assert "keep: 3" in body


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
