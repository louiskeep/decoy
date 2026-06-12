"""V2 schema regression gate for the bundled `decoy templates` set.

CLI.3 commit 1 (2026-06-02): every surviving bundled template must pass
`PipelineConfig.model_validate`. Pre-CLI.3 all five templates were V1
shape (`version: '1.0'` + `masking_rules:` flat list); the V2 validator
hard-rejects them. The graph template was hard-deleted alongside the
storm-reframe-C / S22-CL-V1GRAPHRUNNER engine cleanup.

A new template registration must add a cell here OR explicitly opt out
with a comment naming the V2-incompat reason. Mirrors the canary
pattern from `tests/unit/providers_v2/test_registry.py`
(documented-name allowlist).
"""

from __future__ import annotations

import yaml
from decoy_engine import PipelineConfig

from decoy.templates import get_template, template_names


def test_no_graph_template_registered():
    """The V1 graph template was hard-deleted under CLI.3 (storm-reframe-C
    / S22-CL-V1GRAPHRUNNER precedent). Future re-introductions need an
    explicit V2-shape rewrite."""
    assert "graph" not in template_names()


def test_every_registered_template_loads():
    """Every name in the registry resolves to a real bundled YAML file."""
    for name in template_names():
        template = get_template(name)
        assert template is not None, f"registered template {name!r} did not load"
        assert template.body.strip(), f"template {name!r} body is empty"


def test_minimal_template_validates_under_v2():
    template = get_template("minimal")
    assert template is not None
    PipelineConfig.model_validate(yaml.safe_load(template.body))


def test_hipaa_template_validates_under_v2():
    template = get_template("hipaa")
    assert template is not None
    PipelineConfig.model_validate(yaml.safe_load(template.body))


def test_pci_template_validates_under_v2():
    template = get_template("pci")
    assert template is not None
    PipelineConfig.model_validate(yaml.safe_load(template.body))


def test_gdpr_template_validates_under_v2():
    template = get_template("gdpr")
    assert template is not None
    PipelineConfig.model_validate(yaml.safe_load(template.body))


def test_generate_template_validates_under_v2():
    template = get_template("generate")
    assert template is not None
    parsed = yaml.safe_load(template.body)
    # FC-1 (2026-06-02): top-level `mode:` is gone; the generate template
    # declares its kind by populating every table's `generate_columns`
    # (and no `columns`). The validator enforces XOR at TableConfig.
    cfg = PipelineConfig.model_validate(parsed)
    assert all(t.generate_columns and not t.columns for t in cfg.tables), (
        "the generate template MUST declare every table as generate-kind "
        "(generate_columns populated, columns empty)"
    )


def test_every_template_in_registry_has_a_unit_test():
    """Canary: a new template must add its own cell to this file. Mirrors
    the providers_v2 documented-allowlist pattern -- catches drift at the
    source instead of having every downstream consumer fail mysteriously."""
    expected = {"minimal", "hipaa", "pci", "gdpr", "generate"}
    actual = set(template_names())
    missing = expected - actual
    extra = actual - expected
    assert not missing, f"templates removed from registry without test update: {sorted(missing)}"
    assert not extra, f"templates added without test update: {sorted(extra)}"
