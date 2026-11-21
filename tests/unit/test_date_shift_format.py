"""Date_shift format handling for the shipped templates and `decoy init`.

Every date_shift in a shipped template carries `provider_config.date_format`.
`decoy init` writes one only when the engine reports one format fits every
value (`format_pattern_complete`, reported since engine 0.28.2, which also
refuses a format-less date_shift at plan compile). The cells that stub a match
without the flag cover only the fallback for an older engine; a real 0.28.2
scan always carries the flag.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
import yaml

from decoy.cli._init_inference import (
    _DATE_REDACT,
    _FALLBACK,
    _INFERENCE_TABLE,
    _infer_strategy_for_column,
)
from decoy.cli.project._columns import emit_column_yaml
from decoy.templates import get_template, template_names


def _walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def _date_shift_columns(name: str) -> list[dict]:
    tpl = get_template(name)
    assert tpl is not None
    return [d for d in _walk(yaml.safe_load(tpl.body)) if d.get("strategy") == "date_shift"]


@pytest.mark.parametrize("name", template_names())
def test_every_shipped_template_date_shift_has_date_format(name: str):
    for col in _date_shift_columns(name):
        fmt = (col.get("provider_config") or {}).get("date_format")
        assert isinstance(fmt, str) and fmt.strip(), f"{name}.{col['name']} lacks date_format"


def test_compliance_templates_do_carry_date_shift():
    assert len(_date_shift_columns("hipaa")) == 3
    assert len(_date_shift_columns("pci")) == 1


@dataclass
class _Match:
    detector_id: str
    format_pattern: str | None = None
    match_rate: float = 0.95
    confidence_bucket: str = "high"


@dataclass
class _Stats:
    name: str
    detector_matches: list = field(default_factory=list)
    inferred_type: str = "string"
    is_likely_unique: bool = False


@dataclass
class _StatsComplete(_Stats):
    format_pattern_complete: bool = False


_VARIANTS = [
    ("iso_date", "%Y-%m-%dT%H:%M:%S"),
    ("iso_date", "%Y%m%d"),
    ("us_date", "%m/%d/%y"),
    ("eu_date", "%d.%m.%Y"),
    ("eu_date", "%d-%m-%Y"),
]


@pytest.mark.parametrize(("detector", "fmt"), _VARIANTS)
def test_complete_variant_writes_its_format(detector: str, fmt: str):
    fs = _StatsComplete("d", [_Match(detector, fmt)], format_pattern_complete=True)
    inf = _infer_strategy_for_column(fs)
    assert inf.strategy == "date_shift"
    assert inf.date_format == fmt
    col = yaml.safe_load(emit_column_yaml("d", inf))[0]
    assert col["provider_config"]["date_format"] == fmt
    assert col["provider_config"]["min_days"] == -365


def test_flag_on_top_match_wins_over_field_stats():
    @dataclass
    class _M(_Match):
        format_pattern_complete: bool = True

    fs = _StatsComplete("d", [_M("iso_date", "%Y-%m-%d")], format_pattern_complete=False)
    assert _infer_strategy_for_column(fs).date_format == "%Y-%m-%d"


@pytest.mark.parametrize("detector", ["iso_date", "us_date", "eu_date"])
@pytest.mark.parametrize("fmt", ["%d.%m.%Y", None, "  "])
def test_present_but_not_true_gets_date_redact(detector: str, fmt):
    """Mixed variants, 31.02.2024, padded values, or no format: the engine says
    no single format fits, so redact with the date-specific note."""
    fs = _StatsComplete("d", [_Match(detector, fmt)], format_pattern_complete=False)
    inf = _infer_strategy_for_column(fs)
    assert inf is _DATE_REDACT
    assert inf.strategy == "redact"
    assert "no single format fits every value" in inf.review
    assert "passthrough" not in inf.review


def test_complete_true_without_a_format_gets_date_redact():
    fs = _StatsComplete("d", [_Match("iso_date", None)], format_pattern_complete=True)
    assert _infer_strategy_for_column(fs) is _DATE_REDACT


def test_date_redact_review_is_value_free_and_emits():
    body = emit_column_yaml("d", _DATE_REDACT)
    assert "strategy: redact" in body and "date_format" in body  # the note names the key


def test_engine_without_flag_keeps_origin_main_output_for_dd_mm_slash_data():
    """Stub without the flag (older engine): DD/MM slash data is detected us_date with %m/%d/%Y. Writing that
    format fails 603/1000 rows; today's init writes date_shift with no
    date_format and the engine guesses. That output must not change."""
    inf = _infer_strategy_for_column(_Stats("d", [_Match("us_date", "%m/%d/%Y")]))
    assert inf.strategy == "date_shift"
    assert inf.date_format is None
    assert inf == _INFERENCE_TABLE["us_date"]
    body = emit_column_yaml("d", inf)
    assert "date_format" not in body.split("# REVIEW", 1)[-1].split("\n", 1)[-1]
    # unchanged strategy block, as origin/main writes it
    assert "      - name: d\n        strategy: date_shift\n        namespace: d\n" in body
    assert "          min_days: -365\n          max_days: 365" in body


def test_engine_without_flag_iso_date_has_no_format_and_eu_date_falls_back():
    iso = _infer_strategy_for_column(_Stats("d", [_Match("iso_date", "%Y-%m-%d")]))
    assert iso.strategy == "date_shift" and iso.date_format is None
    assert _infer_strategy_for_column(_Stats("d", [_Match("eu_date", "%d.%m.%Y")])) is _FALLBACK


def test_ambiguous_date_column_keeps_format():
    fs = _StatsComplete(
        "d",
        [_Match("iso_date", "%Y-%m-%d", 0.95), _Match("us_phone", None, 0.92)],
        format_pattern_complete=True,
    )
    inf = _infer_strategy_for_column(fs)
    assert inf.strategy == "date_shift" and inf.date_format == "%Y-%m-%d"


def test_emit_allows_date_shift_without_format_only_for_absent_flag_path():
    """Guard (L2): the writer does not raise on a format-less date_shift. That
    shape is produced only for a stub with no completeness flag. Engine 0.28.2
    reports the flag, so a real scan never reaches it."""
    no_flag = _infer_strategy_for_column(_Stats("d", [_Match("iso_date", "%Y-%m-%d")]))
    assert no_flag.date_format is None
    assert "date_format" not in yaml.safe_load(emit_column_yaml("d", no_flag))[0]["provider_config"]
    flagged = _infer_strategy_for_column(
        _StatsComplete("d", [_Match("iso_date", "%Y-%m-%d")], format_pattern_complete=False)
    )
    assert flagged.strategy != "date_shift"


def test_init_scan_of_real_dates_follows_engine_flag():
    import pandas as pd
    from decoy_engine import profile_columns

    df = pd.DataFrame({"signup": ["2020-01-15", "2020-02-20", "2020-03-05", "2020-04-30"]})
    fs = profile_columns(df, source_label="t").fields[0]
    inf = _infer_strategy_for_column(fs)
    if hasattr(fs, "format_pattern_complete") and fs.format_pattern_complete:
        assert inf.date_format == "%Y-%m-%d"
    elif not hasattr(fs, "format_pattern_complete"):
        assert inf.strategy == "date_shift" and inf.date_format is None


def test_incomplete_date_with_ambiguous_second_detector_keeps_date_note():
    fs = _StatsComplete(
        "d",
        [_Match("iso_date", "%Y-%m-%d", 0.95), _Match("us_phone", None, 0.92)],
        format_pattern_complete=False,
    )
    inf = _infer_strategy_for_column(fs)
    assert inf.strategy == "redact"
    assert inf.date_format is None
    assert _DATE_REDACT.review in inf.review
    assert "no single format fits every value" in inf.review
    assert "multiple candidate signals" in inf.review
    assert "passthrough" not in inf.review
