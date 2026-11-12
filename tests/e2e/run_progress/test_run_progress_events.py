"""`decoy run` hands the engine one progress sink on every route it can take (L5a).

Routes the CLI reaches in engine 0.22.0: the whole-table `run_pipeline` call (mask, generate,
and mixed with a relationship; the engine picks its internal route, full-frame for these sizes)
and the `--rows` preview. `--chunked` calls `run_mask_pipeline_chunked`, which takes no progress
sink in 0.22.0 (it gains one with the RESULT E3 release), so its case is skipped as blocked and
`test_the_chunked_engine_api_still_takes_no_sink` flips when the engine adds the parameter. No
`decoy run` flag forces the engine's sequential or out-of-core route, and the streaming route
needs a transactional sink the CLI never passes.

A recording consumer joins the fan-out through `_progress.build`, as a log writer will (L5b).
"""

from __future__ import annotations

import inspect
import io
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from decoy_engine import PhaseEvent, event_to_dict
from rich.console import Console
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_OK
from decoy.cli.run import _progress
from decoy.ui import output as ui_output
from tests.csv_sources import csv_source
from tests.keyed_secret import TEST_MASK_SECRET_REF

runner = CliRunner()
CANARY = "CANARYc4f1"


class Recorder:
    def __init__(self) -> None:
        self.events: list[Any] = []
        self.fanouts: list[_progress.ProgressFanout] = []

    def __call__(self, event: Any) -> None:
        self.events.append(event)

    def kinds(self) -> list[str]:
        return [event_to_dict(e)["kind"] for e in self.events]


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    rec = Recorder()
    real = _progress.build

    def build() -> _progress.ProgressFanout:
        fanout = real()
        fanout.add(rec)
        rec.fanouts.append(fanout)
        return fanout

    monkeypatch.setattr(_progress, "build", build)
    return rec


@pytest.fixture(autouse=True)
def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mask_secret: str) -> None:
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)


def _csv(path: Path, header: list[str], rows: int) -> Path:
    lines = [",".join(header)]
    lines += [",".join(f"{CANARY}{c}{i}" for c in range(len(header))) for i in range(rows)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _mask_config(tmp_path: Path) -> dict:
    src = _csv(tmp_path / "people.csv", ["pid", "email", "note"], 6)
    return {
        "version": 2,
        "global_settings": {"seed": 1, "mask_secret_ref": TEST_MASK_SECRET_REF},
        "sources": {"people": csv_source(src)},
        "tables": [
            {
                "name": "people",
                "columns": [
                    {"name": "pid", "strategy": "hash", "namespace": "p", "deterministic": True},
                    {"name": "email", "strategy": "redact"},
                    {"name": "note", "strategy": "redact"},
                ],
            }
        ],
        "targets": {"people": {"type": "file", "format": "csv", "path": "people_out.csv"}},
    }


def _generate_config(_tmp_path: Path) -> dict:
    return {
        "version": 2,
        "global_settings": {"seed": 1},
        "tables": [
            {
                "name": "customers",
                "row_count": 8,
                "generate_columns": [
                    {"name": "customer_id", "type": "sequence", "start": 1, "step": 1}
                ],
            }
        ],
        "targets": {"customers": {"type": "file", "format": "csv", "path": "customers.csv"}},
    }


def _mixed_config(tmp_path: Path) -> dict:
    orders = tmp_path / "orders.csv"
    orders.write_text("order_id,customer_id\nO1,1\nO2,2\nO3,3\n", encoding="utf-8")
    cfg = _generate_config(tmp_path)
    cfg["global_settings"]["mask_secret_ref"] = TEST_MASK_SECRET_REF
    cfg["sources"] = {"orders": csv_source(orders)}
    cfg["tables"].append(
        {
            "name": "orders",
            "columns": [
                {"name": "order_id", "strategy": "passthrough"},
                {"name": "customer_id", "strategy": "passthrough"},
            ],
        }
    )
    cfg["relationships"] = [
        {
            "parent": {"table": "customers", "columns": ["customer_id"]},
            "children": [{"table": "orders", "columns": ["customer_id"]}],
            "orphan_policy": "preserve",
            "namespace": "customer_orders",
        }
    ]
    cfg["targets"]["orders"] = {"type": "file", "format": "csv", "path": "orders_out.csv"}
    return cfg


def _write(tmp_path: Path, cfg: dict) -> Path:
    path = tmp_path / "pipeline.yaml"
    path.write_text(yaml.dump(cfg), encoding="utf-8")
    return path


def _run(tmp_path: Path, build: Callable[[Path], dict], *flags: str) -> Any:
    return runner.invoke(app, ["run", str(_write(tmp_path, build(tmp_path))), *flags])


# -- L5a-every-route ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("build", "flags"),
    [
        (_mask_config, ()),
        (_generate_config, ()),
        (_mixed_config, ()),
        (_generate_config, ("--rows", "3")),
    ],
    ids=["whole-table-mask", "whole-table-generate", "mixed-with-relationship", "rows-preview"],
)
def test_every_route_feeds_the_sink(
    tmp_path: Path, recorder: Recorder, build: Callable[[Path], dict], flags: tuple[str, ...]
) -> None:
    """ML5a-route: passing the sink on one route only turns another case red."""
    result = _run(tmp_path, build, *flags)
    assert result.exit_code == EXIT_OK, result.output
    kinds = recorder.kinds()
    assert "phase" in kinds and kinds[-1] == "terminal"
    assert len(recorder.fanouts) == 1  # one sink for the whole command


@pytest.mark.skip(
    reason="blocked by the engine release: run_mask_pipeline_chunked in decoy-engine 0.22.0 "
    "takes no progress sink (RESULT E3 adds it); nothing to pass and no event to test"
)
def test_the_chunked_route_feeds_the_sink(tmp_path: Path, recorder: Recorder) -> None:
    result = _run(tmp_path, _mask_config, "--chunked")
    assert result.exit_code == EXIT_OK, result.output
    assert "phase" in recorder.kinds()


def test_the_chunked_engine_api_still_takes_no_sink() -> None:
    """When this fails, the pinned engine can take a sink on the chunked route: pass it and
    unskip `test_the_chunked_route_feeds_the_sink`."""
    from decoy_engine import run_mask_pipeline_chunked

    params = inspect.signature(run_mask_pipeline_chunked).parameters
    assert "progress" not in params and "chunk_result_sink" in params  # non-vacuous: real API


# -- L5a-order ---------------------------------------------------------------------------------


def test_events_arrive_in_emission_order(tmp_path: Path, recorder: Recorder) -> None:
    result = _run(tmp_path, _mixed_config)
    assert result.exit_code == EXIT_OK, result.output
    seqs = [event_to_dict(e)["sequence"] for e in recorder.events]
    assert len(seqs) >= 3 and all(isinstance(s, int) for s in seqs)
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)


# -- L5a-consumer-fault ------------------------------------------------------------------------


def test_a_failing_consumer_changes_nothing(
    tmp_path: Path, recorder: Recorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ML5a-propagate: letting the consumer's error escape fails the run; red."""
    clean = _run(tmp_path, _mask_config)
    assert clean.exit_code == EXIT_OK, clean.output
    real = _progress.build

    def broken_build() -> _progress.ProgressFanout:
        fanout = real()

        def boom(_event: Any) -> None:
            raise RuntimeError("consumer bug")

        fanout.add(boom)
        recorder.fanouts.append(fanout)
        return fanout

    monkeypatch.setattr(_progress, "build", broken_build)
    result = _run(tmp_path, _mask_config)
    assert result.exit_code == clean.exit_code == EXIT_OK, result.output
    fanout = recorder.fanouts[-1]
    assert fanout.faults == fanout.delivered > 0  # every event hit the bug once, none retried
    outputs = sorted(tmp_path.rglob("people_out.csv"))
    assert len(outputs) == 2  # both runs delivered
    assert outputs[0].read_bytes() == outputs[1].read_bytes()


# -- L5a-quiet-json ----------------------------------------------------------------------------


@pytest.fixture
def terminal_consoles(monkeypatch: pytest.MonkeyPatch) -> None:
    """Consoles that render live progress as a terminal would, so a display is visible."""
    real = ui_output._make_console

    def make(*, stderr: bool) -> Console:
        base = real(stderr=stderr)
        return Console(
            file=base.file, force_terminal=True, theme=None, soft_wrap=True, width=100,
        )  # fmt: skip

    monkeypatch.setattr(ui_output, "_make_console", make)


@pytest.mark.parametrize("flag", ["--json", "--quiet"])
def test_quiet_and_json_keep_stdout_free_of_progress(
    tmp_path: Path, recorder: Recorder, terminal_consoles: None, flag: str
) -> None:
    """ML5a-stdout: rendering progress on stdout turns this red."""
    result = runner.invoke(app, ["run", str(_write(tmp_path, _mask_config(tmp_path))), flag])
    assert result.exit_code == EXIT_OK, result.output
    assert "phase" in recorder.kinds()  # non-display consumers still get every event
    if flag == "--json":
        json.loads(result.stdout)  # stdout is the one JSON document and nothing else
    else:
        assert result.stdout == ""


def test_the_display_renders_phases_on_stderr(tmp_path: Path, terminal_consoles: None) -> None:
    from decoy.ui.output import OutputMode, OutputState
    from decoy.ui.progress import run_progress

    err, out = io.StringIO(), io.StringIO()
    state = OutputState(
        mode=OutputMode.default,
        verbose=False,
        console=Console(file=out, force_terminal=True, width=100),
        err_console=Console(file=err, force_terminal=True, width=100),
    )
    with run_progress(state, "Running mask...") as display:
        display.on_event(PhaseEvent("mask", "start", "people", sequence=1))
        assert "mask" in display.description and "people" in display.description
    assert out.getvalue() == "" and err.getvalue() != ""


# -- L5a-no-value ------------------------------------------------------------------------------


def test_events_carry_no_cell_value(tmp_path: Path, recorder: Recorder) -> None:
    """ML5a-wrap: wrapping events in a CLI object with a message field turns this red."""
    result = _run(tmp_path, _mask_config)
    assert result.exit_code == EXIT_OK, result.output
    assert CANARY in (tmp_path / "people.csv").read_text(encoding="utf-8")  # the data holds it
    assert recorder.events
    assert {type(e).__module__ for e in recorder.events} == {"decoy_engine._progress_events"}
    dumped = json.dumps([event_to_dict(e) for e in recorder.events])
    assert CANARY not in dumped
    assert not any(hasattr(e, "message") for e in recorder.events)
