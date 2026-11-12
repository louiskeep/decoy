"""The run's one progress sink (L5a): a fan-out over the engine's `ProgressSink` protocol.

L5a-order (emission order kept, nothing buffered) and L5a-consumer-fault (a raising consumer is
counted, never retried, and never stops the others), on real engine event objects.
"""

from __future__ import annotations

from decoy.cli.run._progress import ProgressFanout, build
from decoy_engine import PhaseEvent, ProgressSink, TerminalEvent


def _events(n: int) -> list[object]:
    out: list[object] = [
        PhaseEvent("mask", "start" if i % 2 == 0 else "finish", "orders", sequence=i + 1)
        for i in range(n - 1)
    ]
    out.append(TerminalEvent("ok", sequence=n))
    return out


def test_the_fanout_is_an_engine_progress_sink() -> None:
    fanout = build()
    assert isinstance(fanout, ProgressSink) and isinstance(fanout, ProgressFanout)


def test_every_consumer_sees_every_event_in_emission_order() -> None:
    """ML5a-buffer: reordering through a set turns this red."""
    fanout = build()
    first: list[object] = []
    second: list[object] = []
    fanout.add(first.append)
    fanout.add(second.append)
    events = _events(40)
    for event in events:
        fanout.on_event(event)
    assert first == events and second == events  # the same objects, untouched, in order
    assert [e.sequence for e in first] == list(range(1, 41))  # type: ignore[attr-defined]
    assert fanout.delivered == 40


def test_a_consumer_that_raises_is_counted_not_retried_and_others_still_get_events() -> None:
    """ML5a-propagate: letting the consumer's error escape turns this red."""
    fanout = build()
    calls: list[object] = []
    after: list[object] = []

    def broken(event: object) -> None:
        calls.append(event)
        raise RuntimeError("a consumer bug")

    fanout.add(broken)
    fanout.add(after.append)
    events = _events(5)
    for event in events:
        fanout.on_event(event)  # never raises
    assert calls == events  # one call per event: no retry
    assert after == events
    assert fanout.faults == 5


def test_a_fanout_with_no_consumer_accepts_events() -> None:
    fanout = build()
    for event in _events(3):
        fanout.on_event(event)
    assert (fanout.delivered, fanout.faults) == (3, 0)
