"""`decoy.mask(native=...)` (Phase 3.1): the library mirrors `decoy run`'s
`--native`/`--no-native` through the SAME shared gate
(`decoy._native_gate`), so it cannot silently write an ineligible-shape
result the CLI would refuse.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from decoy_engine import NativeCompanionStatus

import decoy
from decoy._native_gate import NativeGateError

_ABI = "decoy-native-abi-2"


def _status(
    reason: str, *, present: bool, ok: bool, abi_actual: str | None = None
) -> NativeCompanionStatus:
    return NativeCompanionStatus(
        present=present,
        ok=ok,
        abi_expected=_ABI,
        abi_actual=abi_actual,
        version="9.9.9" if present else None,
        reason=reason,
        cause=None,
    )


def _patch(monkeypatch: pytest.MonkeyPatch, status: NativeCompanionStatus) -> None:
    monkeypatch.setattr("decoy_engine.native_companion_status", lambda: status)


@pytest.fixture
def eligible_parquet_config(tmp_path: Path) -> dict:
    src = tmp_path / "in.parquet"
    pd.DataFrame({"id": ["a", "b", "c"], "email": ["a@x.com", "b@x.com", "c@x.com"]}).to_parquet(
        src, index=False
    )
    return {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {"customers": {"type": "file", "format": "parquet", "path": str(src)}},
        "tables": [
            {
                "name": "customers",
                "columns": [
                    {"name": "id", "strategy": "passthrough"},
                    {"name": "email", "strategy": "hash", "namespace": "email_ns"},
                ],
            }
        ],
        "targets": {
            "customers": {"type": "file", "format": "csv", "path": str(tmp_path / "out.csv")}
        },
    }


@pytest.fixture
def csv_config(tmp_path: Path) -> dict:
    """Non-Parquet source: coarse candidate, not static-eligible."""
    src = tmp_path / "in.csv"
    pd.DataFrame({"id": ["a", "b"], "email": ["a@x.com", "b@x.com"]}).to_csv(src, index=False)
    return {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {"customers": {"type": "file", "format": "csv", "path": str(src)}},
        "tables": [
            {
                "name": "customers",
                "columns": [
                    {"name": "id", "strategy": "passthrough"},
                    {"name": "email", "strategy": "hash", "namespace": "email_ns"},
                ],
            }
        ],
        "targets": {
            "customers": {"type": "file", "format": "csv", "path": str(tmp_path / "out.csv")}
        },
    }


def test_mask_default_native_falls_back_silently(eligible_parquet_config: dict, tmp_path: Path):
    out = decoy.mask(config=eligible_parquet_config)
    assert isinstance(out, pd.DataFrame)
    assert (tmp_path / "out.csv").exists()


def test_mask_native_true_uses_shared_gate_absent_companion(
    eligible_parquet_config: dict, tmp_path: Path
):
    with pytest.raises(NativeGateError) as exc_info:
        decoy.mask(config=eligible_parquet_config, native=True)
    assert exc_info.value.code.startswith("native_require_")
    assert not (tmp_path / "out.csv").exists()


def test_mask_native_true_refuses_broken_companion(
    eligible_parquet_config: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _patch(monkeypatch, _status("kat-corrupt", present=True, ok=False, abi_actual=_ABI))
    with pytest.raises(NativeGateError):
        decoy.mask(config=eligible_parquet_config, native=True)
    assert not (tmp_path / "out.csv").exists()


def test_mask_native_false_forces_legacy_pandas(eligible_parquet_config: dict, tmp_path: Path):
    out = decoy.mask(config=eligible_parquet_config, native=False)
    assert isinstance(out, pd.DataFrame)
    assert (tmp_path / "out.csv").exists()


def test_mask_default_broken_companion_fails_closed_no_return(
    eligible_parquet_config: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Mirrors `decoy run`'s default-intent fail-closed-on-broken-companion
    behavior: `mask()` returns no DataFrame and writes no output."""
    _patch(monkeypatch, _status("abi-mismatch", present=True, ok=False, abi_actual="v1"))
    with pytest.raises(NativeGateError):
        decoy.mask(config=eligible_parquet_config)
    assert not (tmp_path / "out.csv").exists()


def test_mask_native_true_fails_closed_on_runtime_ineligible_candidate(
    csv_config: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Stage 1 passes (companion reported healthy); the job runs, then fails
    closed post-run with no compiled-kernel evidence -- returns no
    DataFrame, writes no output, the SAME outcome `decoy run --native`
    gives for the same shape (P1-3)."""
    _patch(monkeypatch, _status("present-ok", present=True, ok=True, abi_actual=_ABI))
    with pytest.raises(NativeGateError) as exc_info:
        decoy.mask(config=csv_config, native=True)
    assert exc_info.value.code == "native_require_no_evidence"
    assert not (tmp_path / "out.csv").exists()


def test_mask_native_true_on_generate_only_rejected_before_dispatch(tmp_path: Path):
    config = {
        "version": 1,
        "global_settings": {"seed": 42},
        "tables": [
            {
                "name": "employees",
                "row_count": 3,
                "generate_columns": [{"name": "id", "type": "sequence", "start": 1, "step": 1}],
            }
        ],
        "targets": {
            "employees": {"type": "file", "format": "csv", "path": str(tmp_path / "gen.csv")}
        },
    }
    with pytest.raises(NativeGateError) as exc_info:
        decoy.mask(config=config, native=True)
    assert exc_info.value.code == "native_require_not_a_candidate"
    assert not (tmp_path / "gen.csv").exists()
