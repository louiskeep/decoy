"""V2 schema regression gate for the bundled `examples/` set (OSS-CODE-5).

CLI.3 refreshed `src/decoy/templates/*.yaml` to V2 shape; the `examples/`
folder was explicitly left to "CLI.4 docs territory" and CLI.4 did not
touch it either. The result was three live V1-shape examples
(`mask_example.yaml`, `generate_example.yaml`, `fixed_width_example.yaml`)
plus `graph_example.yaml` (V1 graph mode, dead under the clean break)
sitting in the public repo as the first thing an external contributor
would open.

OSS.1 commit 2 (2026-06-02) rewrote the two surviving examples to V2
shape and hard-deleted the two V1-only files (`graph_example.yaml` per
the clean-break rule; `fixed_width_example.yaml` because V2 has no
fixed-width source format, so the example could not be made to
validate -- Dennis spec D1 default of "keep at root, validate" was
impossible to honor for that one).

A new `examples/*.yaml` file must validate against `PipelineConfig`
OR be added to the explicit skip set with a documented reason. The
mirror to this file is `tests/unit/test_bundled_templates.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from decoy_engine import PipelineConfig

EXAMPLES_ROOT = Path(__file__).resolve().parent.parent.parent / "examples"

EXPECTED_EXAMPLES = {"mask_example.yaml", "generate_example.yaml"}


def _example_paths() -> list[Path]:
    return sorted(p for p in EXAMPLES_ROOT.glob("*.yaml"))


def test_expected_examples_present_no_v1_holdovers():
    """The examples folder ships exactly the files this test pins. A
    future re-introduction of a V1 file (e.g. graph_example) requires
    deliberate edits here, not a silent revival."""
    actual = {p.name for p in _example_paths()}
    assert actual == EXPECTED_EXAMPLES, (
        f"Examples drift: missing={EXPECTED_EXAMPLES - actual}, "
        f"extra={actual - EXPECTED_EXAMPLES}"
    )


@pytest.mark.parametrize("path", _example_paths(), ids=lambda p: p.name)
def test_bundled_examples_validate_under_v2_pipeline_config(path: Path):
    """Every shipped example must pass `PipelineConfig.model_validate`.
    Catches drift where a contributor edits an example and inadvertently
    breaks the V2 schema (e.g. reverts to `version: '1.0'` or adds a
    `masking_rules:` block)."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    PipelineConfig.model_validate(raw)


@pytest.mark.parametrize("path", _example_paths(), ids=lambda p: p.name)
def test_bundled_examples_use_supported_modes_only(path: Path):
    """Each example's `mode` field is one of the supported V2 values.
    Rejects V1 `mode: graph` (deleted under clean-break) and
    `mode: convert` (deleted with the CSV-to-Parquet converter)."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    cfg = PipelineConfig.model_validate(raw)
    assert cfg.mode in {"mask", "generate"}, (
        f"{path.name} declares unsupported mode {cfg.mode!r}; "
        f"only mask + generate ship in V2."
    )
