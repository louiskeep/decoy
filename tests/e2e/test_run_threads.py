"""`decoy run --threads` / `decoy.mask(threads=)` (parity C1c).

The engine's native kernels take a `native_threads` grant (default 1). The
CLI never set it, so a user with the companion installed ran single-threaded.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

import decoy
from decoy import _native_gate
from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_USAGE

runner = CliRunner()


def _config(tmp_path: Path) -> Path:
    src = tmp_path / "in.csv"
    pd.DataFrame({"email": ["a@x.com", "b@x.com"]}).to_csv(src, index=False)
    cfg = {
        "version": 1,
        "global_settings": {"seed": 1},
        "sources": {"t": {"type": "file", "format": "csv", "path": str(src)}},
        "tables": [{"name": "t", "columns": [{"name": "email", "strategy": "hash", "namespace": "e"}]}],
        "targets": {"t": {"type": "file", "format": "csv", "path": str(tmp_path / "out.csv")}},
    }
    p = tmp_path / "pipeline.yaml"
    p.write_text(yaml.safe_dump(cfg))
    return p


def test_explicit_threads_are_passed_and_reported(tmp_path: Path, monkeypatch) -> None:
    seen: dict = {}
    import decoy_engine

    original = decoy_engine.run_pipeline

    @functools.wraps(original)
    def spy(*args, **kwargs):
        seen.update(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr("decoy_engine.run_pipeline", spy)
    result = runner.invoke(app, ["run", str(_config(tmp_path)), "--threads", "3", "--json"])
    assert result.exit_code == 0, result.output
    assert seen["native_threads"] == 3
    assert json.loads(result.stdout)["native_threads"] == 3


def test_threads_one_is_the_engine_default_and_not_sent(tmp_path: Path, monkeypatch) -> None:
    seen: dict = {}
    import decoy_engine

    original = decoy_engine.run_pipeline

    @functools.wraps(original)
    def spy(*args, **kwargs):
        seen.update(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr("decoy_engine.run_pipeline", spy)
    result = runner.invoke(app, ["run", str(_config(tmp_path)), "--threads", "1", "--json"])
    assert result.exit_code == 0, result.output
    assert "native_threads" not in seen
    assert json.loads(result.stdout)["native_threads"] == 1


@pytest.mark.parametrize("bad", ["0", "-2"])
def test_non_positive_threads_is_a_usage_error(tmp_path: Path, bad: str) -> None:
    result = runner.invoke(app, ["run", str(_config(tmp_path)), "--threads", bad])
    assert result.exit_code == EXIT_USAGE, result.output
    assert "positive integer" in result.output
    assert not (tmp_path / "out.csv").exists()


def test_default_is_one_without_a_companion(monkeypatch) -> None:
    class _Status:
        ok = False

    monkeypatch.setattr("decoy_engine.native_companion_status", lambda: _Status())
    assert _native_gate.resolve_native_threads(None) == 1


def test_default_caps_at_the_knee_with_a_companion(monkeypatch) -> None:
    class _Status:
        ok = True

    monkeypatch.setattr("decoy_engine.native_companion_status", lambda: _Status())
    monkeypatch.setattr("os.cpu_count", lambda: 64)
    assert _native_gate.resolve_native_threads(None) == 4


def test_kwargs_are_omitted_on_an_engine_without_the_knob(monkeypatch) -> None:
    import decoy_engine

    def old_run_pipeline(config, sources=None, *, engine_version):  # pragma: no cover - signature only
        raise AssertionError

    monkeypatch.setattr(decoy_engine, "run_pipeline", old_run_pipeline)
    assert _native_gate.native_threads_kwargs(3) == {}


def test_mask_api_accepts_threads(tmp_path: Path, monkeypatch) -> None:
    seen: dict = {}
    import decoy_engine

    original = decoy_engine.run_pipeline

    @functools.wraps(original)
    def spy(*args, **kwargs):
        seen.update(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr("decoy_engine.run_pipeline", spy)
    out = decoy.mask(config=_config(tmp_path), threads=2)
    assert isinstance(out, pd.DataFrame)
    assert seen["native_threads"] == 2
