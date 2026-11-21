"""C1l: `classify_route` reads the lane's compiled-kernel evidence when no unified slice ran."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from decoy import _native_gate

_LANE = {"execution": {"execution_mode": "full_frame"}}


def _summary(route: str, native_executed: bool | None) -> SimpleNamespace:
    return SimpleNamespace(route=route, native_executed=native_executed)


@pytest.mark.parametrize(
    ("executed", "state"), [(True, "native"), (False, "pandas"), (None, "pandas")]
)
def test_lane_run_takes_state_from_native_executed(
    monkeypatch: pytest.MonkeyPatch, executed: bool | None, state: str
) -> None:
    monkeypatch.setattr("decoy_engine.route_summary", lambda qm: _summary("auto_chunk", executed))
    route = _native_gate.classify_route(chunked=False, any_generate=False, quality_metrics=_LANE)
    assert route.applicable and route.state == state


def test_native_lane_passes_the_require_check(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("decoy_engine.route_summary", lambda qm: _summary("auto_chunk", True))
    route = _native_gate.classify_route(chunked=False, any_generate=False, quality_metrics=_LANE)
    _native_gate.post_run_verify(intent="require", route=route)


def test_lane_without_compiled_evidence_refuses_require(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("decoy_engine.route_summary", lambda qm: _summary("auto_chunk", False))
    route = _native_gate.classify_route(chunked=False, any_generate=False, quality_metrics=_LANE)
    with pytest.raises(_native_gate.NativeGateError, match="no output was written"):
        _native_gate.post_run_verify(intent="require", route=route)


def test_other_routes_keep_the_legacy_label(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("decoy_engine.route_summary", lambda qm: _summary("full_frame", None))
    route = _native_gate.classify_route(chunked=False, any_generate=False, quality_metrics=_LANE)
    assert route.state == "pandas"
