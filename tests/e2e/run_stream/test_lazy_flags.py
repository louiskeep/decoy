"""AT-C1l flag cells, AT-C1f and the `--native` decline cells on a plain single-table run.

Parity cells compare the lazy run with the base resident run: exit, route and every file the
run places (targets and the quarantine file).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from typer.testing import CliRunner

from decoy.__main__ import app
from tests.e2e.run_stream._support import (
    PLAIN,
    install_probe,
    run_both,
    single_build,
    write_config,
)
from tests.keyed_secret import secret_env


@pytest.fixture(autouse=True)
def _secret(monkeypatch: pytest.MonkeyPatch) -> None:
    for var, value in secret_env().items():
        monkeypatch.setenv(var, value)


def _same(lazy: Any, base: Any) -> None:
    assert lazy.exit_code == base.exit_code, (lazy.output, base.output)
    assert lazy.route == base.route
    assert lazy.files == base.files


@pytest.mark.parametrize(
    "flag", ["--explain-plan", "--fidelity", "--post-validate", "--post-validate-enforce"]
)
def test_report_flag_parity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, flag: str) -> None:
    lazy, base, _ = run_both(
        monkeypatch, tmp_path, single_build(tmp_path, columns=PLAIN), args=(flag,)
    )
    assert lazy.exit_code == 0, lazy.output
    _same(lazy, base)


def test_quarantine_parity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cols = [{"name": "id", "strategy": "passthrough"}, {"name": "email", "strategy": "passthrough"}]
    single = single_build(tmp_path, columns=cols)

    def build(out: Path) -> tuple[Path, list[Path]]:
        # Rows whose email does not start `user1` fail the validator and go to quarantine.
        config, targets = single(out)
        import yaml

        cfg = yaml.safe_load(config.read_text(encoding="utf-8"))
        cfg["validators"] = [
            {
                "name": "regex_match",
                "columns": {"people": ["email"]},
                "params": {"pattern": "^user1"},
            }
        ]
        cfg["quarantine"] = {
            "enabled": True,
            "output_path": str(out / "q.jsonl"),
            "triggers": ["validation_fail"],
        }
        return write_config(config, cfg), [*targets, out / "q.jsonl"]

    lazy, base, _ = run_both(monkeypatch, tmp_path, build)
    _same(lazy, base)
    assert lazy.exit_code == 0, lazy.output
    assert "q.jsonl" in lazy.files


def test_targetless_table_parity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A table with no target is consumed and counted, never written."""
    import yaml

    from tests.e2e.run_stream._support import fk_build

    inner = fk_build(tmp_path, rows=100)

    def build(out: Path) -> tuple[Path, list[Path]]:
        config, _ = inner(out)
        cfg = yaml.safe_load(config.read_text(encoding="utf-8"))
        del cfg["targets"]["b"]
        return write_config(config, cfg), [out / "a.csv", out / "b.csv"]

    lazy, base, _ = run_both(monkeypatch, tmp_path, build)
    assert lazy.exit_code == 0, lazy.output
    _same(lazy, base)
    assert set(lazy.files) == {"a.csv"}


def test_file_changed_after_the_facts_pass_exits_3_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AT-C1f: the source is replaced after routing read its footer and before the first batch."""
    from decoy_engine.profile import LazySource

    install_probe(monkeypatch, chunk_rows=500)  # small chunks put the run on the streamed lane
    build = single_build(tmp_path, columns=PLAIN)
    out = tmp_path / "run"
    out.mkdir()
    config, targets = build(out)
    source = tmp_path / "data" / "people.parquet"
    real = LazySource.open_batches
    swapped: list[bool] = []

    def swap_then_open(self: Any, *args: Any, **kwargs: Any) -> Any:
        if not swapped:
            swapped.append(True)
            pq.write_table(pa.table({"id": [1], "email": ["x@example.invalid"]}), source)
        return real(self, *args, **kwargs)

    monkeypatch.setattr(LazySource, "open_batches", swap_then_open)
    result = CliRunner().invoke(app, ["run", str(config)])
    assert swapped, result.output
    assert result.exit_code == 3, result.output
    assert not targets[0].exists()
    assert "x@example.invalid" not in result.output


_COMPANION = importlib.util.find_spec("decoy_engine_native") is not None


@pytest.mark.skipif(not _COMPANION, reason="needs a real compiled decoy-engine-native companion")
@pytest.mark.parametrize(
    "columns",
    [
        # No column the companion can plan: nothing compiled runs, so --native has no evidence.
        [{"name": "id", "strategy": "passthrough"}, {"name": "email", "strategy": "redact"}],
        # A Python-planned column beside a compiled one: the run still has to name the evidence.
        [
            {"name": "id", "strategy": "passthrough"},
            {"name": "email", "strategy": "faker", "provider": "person_email"},
        ],
    ],
    ids=["redact-only", "faker-only"],
)
def test_native_decline_refuses_with_no_output(tmp_path: Path, columns: list[dict]) -> None:
    build = single_build(tmp_path, columns=columns)
    out = tmp_path / "run"
    out.mkdir()
    config, targets = build(out)
    result = CliRunner().invoke(app, ["run", str(config), "--native", "--json"])
    assert result.exit_code != 0, result.output
    assert "no output was written" in " ".join(result.output.split())
    assert not targets[0].exists()
    doc = json.loads(result.stdout) if result.stdout.strip().startswith("{") else {}
    assert doc.get("code", "native_require_no_evidence") == "native_require_no_evidence"
