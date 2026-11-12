"""The run's one progress sink: a fan-out over the engine's `ProgressSink` protocol (LIB L5a).

`run_pipeline(progress=...)` takes one sink. Several things want the same events: the terminal
display now, the job-log writer later (L5b). The engine sees this one object, and it forwards each
event, unchanged and in the order the engine emitted it, to every registered consumer, the
observer pattern the engine's own `StructuredEventsSink` follows.

A consumer is a callable that takes one event. One that raises is counted in `faults` and skipped
for that event, never retried, so a broken display or log can never change the run's outcome or
exit code. Nothing is added to an event: consumers get the engine's own value-free objects
(sanitized names, registered codes, error class names only).
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

__all__ = ["Consumer", "ProgressFanout", "build", "run_pipeline_kwargs"]

Consumer = Callable[[Any], None]


class ProgressFanout:
    """The `ProgressSink` handed to the engine; forwards every event to every consumer."""

    def __init__(self) -> None:
        self._consumers: list[Consumer] = []
        self.delivered = 0
        self.faults = 0

    def add(self, consumer: Consumer) -> None:
        self._consumers.append(consumer)

    def on_event(self, event: Any) -> None:
        self.delivered += 1
        for consumer in self._consumers:
            try:
                consumer(event)
            except Exception:  # a consumer's bug must not reach the engine or the run
                self.faults += 1


def build() -> ProgressFanout:
    """The one sink for a `decoy run` command."""
    return ProgressFanout()


def run_pipeline_kwargs(run_pipeline: Callable[..., Any], fanout: ProgressFanout | None) -> dict:
    """`{"progress": fanout}` when this engine's `run_pipeline` takes a sink, else nothing.

    The same capability check `_native_gate.run_pipeline_kwargs` uses: the pinned engine (0.22.0)
    takes `progress`, and an older one still runs, with no events, instead of failing on the
    keyword (tests/e2e/test_run_native.py holds that contract).
    """
    if fanout is None or "progress" not in inspect.signature(run_pipeline).parameters:
        return {}
    return {"progress": fanout}
