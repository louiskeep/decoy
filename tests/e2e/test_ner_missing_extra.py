"""End-to-end test for the NER `[ner]`-extra message through a real
`decoy validate config` invocation (dennis H1, 2026-09-25).

The existing unit test (tests/unit/test_extras.py) constructed a
NerUnavailableError directly, which doesn't prove the message a real
invocation shows: `compile_plan` (`plan/_checks.py`,
`check_text_redact_ner_available`) catches `NerUnavailableError` and
re-raises it wrapped in `PlanCompileError(code=exc.code, ...)`, so the raw
`NerUnavailableError` case a hand-constructed test exercises never reaches
the CLI in practice. This test goes through the real compile path
(`decoy validate config`, config + installed-package check only, no model
load and no profile per `_check_ner_available_for_strategy`'s docstring) so
the wrapped shape is what's actually under test.

Monkeypatches `decoy_engine.storm.ner.spacy_installed` to return False --
the same boundary-level determinism as `_simulate_no_cloud_extra` in
tests/e2e/test_run_missing_extras.py, rather than depending on whether
spaCy happens to be installed in the dev/CI venv running this suite.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_USAGE

runner = CliRunner()


def _ner_pipeline(tmp_path: Path) -> Path:
    src = tmp_path / "notes.csv"
    src.write_text("notes\nCall John Smith at 555-1234.\n", encoding="utf-8")
    cfg = {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {"notes": {"type": "file", "format": "csv", "path": str(src)}},
        "tables": [
            {
                "name": "notes",
                "columns": [
                    {
                        "name": "notes",
                        "strategy": "text_redact",
                        "provider_config": {"ner": {"model": "en_core_web_sm"}},
                    },
                ],
            }
        ],
        "targets": {"notes": {"type": "file", "format": "csv", "path": str(tmp_path / "out.csv")}},
    }
    p = tmp_path / "pipeline.yaml"
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return p


class TestNerMissingExtraThroughRealCompile:
    def test_validate_config_shows_cli_extra_not_engine_extra(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("decoy_engine.storm.ner.spacy_installed", lambda: False)
        cfg = _ner_pipeline(tmp_path)
        result = runner.invoke(app, ["validate", "config", str(cfg)])
        assert result.exit_code == EXIT_USAGE, result.output
        collapsed = " ".join(result.output.split())
        assert "pip install decoy-cli[ner]" in collapsed, result.output
        # The regression this test exists to catch: before the H1 fix, this
        # showed the engine's own message pointing at `decoy-engine[ner]`,
        # wrong for someone who installed decoy-cli, not decoy-engine
        # directly.
        assert "decoy-engine[ner]" not in collapsed, result.output

    def test_validate_config_json_mode_shows_cli_extra(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("decoy_engine.storm.ner.spacy_installed", lambda: False)
        cfg = _ner_pipeline(tmp_path)
        result = runner.invoke(app, ["validate", "config", str(cfg), "--json"])
        assert result.exit_code == EXIT_USAGE, result.output
        assert "pip install decoy-cli[ner]" in result.output, result.output
        assert "decoy-engine[ner]" not in result.output, result.output

    def test_model_not_installed_leaves_engine_message_untranslated(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # spaCy present, just not the requested model: the fix is `spacy
        # download <model>`, not an extra -- the engine's own message
        # should reach the operator unchanged (translate_ner_unavailable
        # only rewrites ner_spacy_not_installed).
        monkeypatch.setattr("decoy_engine.storm.ner.spacy_installed", lambda: True)
        monkeypatch.setattr("decoy_engine.storm.ner.model_installed", lambda model: False)
        cfg = _ner_pipeline(tmp_path)
        result = runner.invoke(app, ["validate", "config", str(cfg)])
        assert result.exit_code == EXIT_USAGE, result.output
        collapsed = " ".join(result.output.split())
        assert "spacy download" in collapsed, result.output
        assert "pip install decoy-cli[ner]" not in collapsed, result.output
