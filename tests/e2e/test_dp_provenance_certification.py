"""Environment-aware certification test for the DP proof-stack gate.

`decoy_engine.quality.dp.fit_dp_snapshot` only completes on a certified
`(platform, cpython, fingerprint)` row (see
`decoy_engine.quality.dp_provenance._CERTIFIED_STACKS`). Which arm this test
takes depends on which venv runs it, so it computes the CURRENT interpreter's
row and looks it up rather than assuming an answer:

- Under `.venv` (this repo's normal dev/test env, with pytest/ruff/mypy
  installed), the fingerprint is not a certified row, so a real fit must
  raise `ProvenanceError(code="dp_stack_uncertified")`. That is the arm this
  test exercises in CI and local `pytest` runs on Linux x86-64. On any other
  platform (macOS) the engine refuses first with `dp_platform_uncertified`;
  `tests/dp_env.py` names the code the host earns.
- Under `.venv-certified` (the pristine runtime-only install pinned by
  `requirements-certified.txt`), the fingerprint IS certified, so a real fit
  must complete and emit schema `dps-marginal/v3`. `scripts/cert_smoke.py`
  covers that arm end to end outside pytest, since `.venv-certified` has no
  pytest to run this file with.

Either way the assertion is the SAME real call; only the environment differs.
"""

from __future__ import annotations

import pandas as pd
import pytest
from decoy_engine.quality import dp_provenance
from decoy_engine.quality.dp import fit_dp_snapshot
from decoy_engine.quality.dp_provenance import ProvenanceError

from tests.dp_env import current_row_is_certified, expected_dp_refusal_code, foreign_platform


def _fit_a_small_frame():
    df = pd.DataFrame(
        {
            "amount": [10.5, 22.1, 9.9, 100.0, 55.2, 31.4, 18.8, 42.0] * 5,
            "is_active": [True, False, True, True, False, True, False, False] * 5,
        }
    )
    column_schema = {
        "amount": {"kind": "numeric", "carrier": "number", "bounds": [0.0, 150.0]},
        "is_active": {"kind": "categorical", "carrier": "flag"},
    }
    return fit_dp_snapshot(df, column_schema, epsilon=8.0, delta=1e-5)


def test_dp_fit_matches_this_environments_certification_status() -> None:
    if current_row_is_certified():
        artifact = _fit_a_small_frame()
        assert artifact["dp"]["schema"] == "dps-marginal/v3"
    else:
        with pytest.raises(ProvenanceError) as exc:
            _fit_a_small_frame()
        assert exc.value.code == expected_dp_refusal_code()


@pytest.mark.parametrize("platform", ["host", "foreign"])
def test_the_expected_code_helper_matches_the_engine_gate(
    platform: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The helper mirrors the engine's own gate, so an engine change in order or codes
    fails here first instead of silently skewing every refusal test."""
    if platform == "foreign":
        monkeypatch.setattr(dp_provenance, "current_platform", foreign_platform)
    expected = expected_dp_refusal_code()
    if platform == "foreign":
        assert expected == "dp_platform_uncertified"
    if expected is None:
        dp_provenance.check_fit_environment()
        return
    with pytest.raises(ProvenanceError) as exc:
        dp_provenance.check_fit_environment()
    assert exc.value.code == expected
