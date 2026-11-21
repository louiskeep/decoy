"""AT-C1l relationship cells: a job the engine cannot keep bounded falls back correctly.

Every cell builds a parent and child job that out-of-core would admit (text keys), adds one
disqualifier, and asserts the lazy run (candidates plus `resident_fallback=True`) against the
base resident run: same exit, same route, same target bytes. A job that finishes also keeps
its keys intact and every row; a job that refuses leaves no target file behind. Where the plan
names a read-whole fallback, the pre-pass spy must see each table read once.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

import pytest
from decoy_engine.profile import LazySource

from tests.e2e.run_stream._support import fk_build, install_probe, run_both
from tests.keyed_secret import secret_env

_ROWS = 300


@pytest.fixture(autouse=True)
def _secret(monkeypatch: pytest.MonkeyPatch) -> None:
    for var, value in secret_env().items():
        monkeypatch.setenv(var, value)


def _rows(raw: bytes) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))


def _check_equal(lazy: Any, base: Any) -> None:
    assert lazy.exit_code == base.exit_code, (lazy.output, base.output)
    assert lazy.route == base.route
    assert lazy.files == base.files


def _check_intact(lazy: Any, *, extra_child_rows: int = 0, orphans: int = 0) -> None:
    """Every source row survives and each child key still names a parent key, bar `orphans`."""
    parents = _rows(lazy.files["a.csv"])
    children = _rows(lazy.files["b.csv"])
    assert len(parents) == _ROWS
    assert len(children) == _ROWS + extra_child_rows
    parent_keys = {r["id"] for r in parents}
    unresolved = [r for r in children if r["a_id"] not in parent_keys]
    assert len(unresolved) == orphans


def _fallback_cell(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    args: tuple[str, ...] = (),
    **build_kwargs: Any,
) -> tuple[Any, Any, Any]:
    probe = install_probe(monkeypatch)
    build = fk_build(tmp_path, rows=_ROWS, **build_kwargs)
    return run_both(monkeypatch, tmp_path, build, args=args, probe=probe)


def _whole(seen: Any, tables: int = 2) -> None:
    """The pre-pass read each table whole, once, and the routes never read a lazy source."""
    assert seen is not None
    assert len(seen.prepass_reads) == tables
    assert all(issubclass(t, LazySource) for t in seen.prepass_reads)
    assert not seen.lazy_materialized


def test_control_job_stays_lazy_out_of_core(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lazy, base, seen = _fallback_cell(monkeypatch, tmp_path)
    assert lazy.exit_code == 0, lazy.output
    _check_equal(lazy, base)
    assert lazy.route == "out_of_core"
    assert seen is not None
    assert seen.prepass_reads == []
    _check_intact(lazy)


def test_cycle_reads_whole_and_takes_full_frame(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lazy, base, seen = _fallback_cell(monkeypatch, tmp_path, cycle=True)
    _check_equal(lazy, base)
    assert lazy.route != "out_of_core"
    if lazy.exit_code == 0:
        _whole(seen)
        _check_intact(lazy)
    else:
        assert lazy.files == {}


@pytest.mark.parametrize("policy", ["fail", "preserve", "remap"])
def test_introduced_orphan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, policy: str) -> None:
    lazy, base, _ = _fallback_cell(monkeypatch, tmp_path, orphan=True, orphan_policy=policy)
    _check_equal(lazy, base)
    if lazy.exit_code == 0:
        _check_intact(lazy, extra_child_rows=1, orphans=1)
    else:
        # A refusal leaves nothing half-written.
        assert lazy.files == {}


def test_orphan_under_the_integrity_gate_blocks_like_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lazy, base, _ = _fallback_cell(
        monkeypatch,
        tmp_path,
        orphan=True,
        extra={"post_scan": {"integrity": True}},
    )
    _check_equal(lazy, base)
    if lazy.exit_code != 0:
        assert lazy.files == {} or set(lazy.files) == set(base.files)


def test_introduced_orphan_under_the_integrity_gate_blocks_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The engine keeps child keys matched by construction, so (as its own tests do) the defect
    # is planted at the gate's input: every child key is rewritten after the mask.
    import pyarrow as pa
    from decoy_engine.execution.pipeline import _post_scan

    real = _post_scan.PostScanGate.run_resident

    def break_child_keys(self: Any, outputs: Any, *args: Any, **kwargs: Any) -> None:
        child = outputs["b"]
        at = child.schema.get_field_index("a_id")
        field = child.schema.field("a_id")
        broken = child.set_column(at, field, pa.array(["no-parent"] * child.num_rows, field.type))
        real(self, {**outputs, "b": broken}, *args, **kwargs)

    monkeypatch.setattr(_post_scan.PostScanGate, "run_resident", break_child_keys)
    lazy, base, _ = _fallback_cell(
        monkeypatch, tmp_path, text_keys=False, extra={"post_scan": {"integrity": True}}
    )
    _check_equal(lazy, base)
    assert lazy.exit_code == 4, lazy.output
    assert lazy.files == {}


def test_integrity_gate_on_a_clean_job_passes_like_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lazy, base, _ = _fallback_cell(monkeypatch, tmp_path, extra={"post_scan": {"integrity": True}})
    assert lazy.exit_code == 0, lazy.output
    _check_equal(lazy, base)
    _check_intact(lazy)


def test_tee_unsupported_defers_the_gate_like_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from decoy_engine.execution.pipeline import _post_scan

    monkeypatch.setattr(_post_scan, "tee_supported", lambda: False)
    lazy, base, _ = _fallback_cell(
        monkeypatch,
        tmp_path,
        text_keys=False,
        extra={"post_scan": {"integrity": True}},
    )
    _check_equal(lazy, base)
    if lazy.exit_code == 0:
        _check_intact(lazy)


# One cell per `_sequential_eligible` disqualifier the CLI can reach.


def test_disqualifier_generate_table(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lazy, base, seen = _fallback_cell(monkeypatch, tmp_path, generate_table=True)
    assert lazy.exit_code == 0, lazy.output
    _check_equal(lazy, base)
    _check_intact(lazy)
    assert seen is not None
    assert seen.prepass_reads  # at least the mask tables of the job


def test_disqualifier_validators(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lazy, base, seen = _fallback_cell(
        monkeypatch, tmp_path, extra={"validators": [{"name": "fk_intact"}]}
    )
    assert lazy.exit_code == 0, lazy.output
    _check_equal(lazy, base)
    _check_intact(lazy)
    _whole(seen)


def test_disqualifier_fidelity_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lazy, base, seen = _fallback_cell(monkeypatch, tmp_path, args=("--fidelity",))
    assert lazy.exit_code == 0, lazy.output
    _check_equal(lazy, base)
    _check_intact(lazy)
    _whole(seen)


def test_disqualifier_post_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lazy, base, seen = _fallback_cell(monkeypatch, tmp_path, args=("--post-validate",))
    assert lazy.exit_code == 0, lazy.output
    _check_equal(lazy, base)
    _check_intact(lazy)
    _whole(seen)


def test_disqualifier_model_post_scan_ask(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lazy, base, seen = _fallback_cell(
        monkeypatch,
        tmp_path,
        extra={"post_scan": {"integrity": True, "detectors": ["regex", "classifier"]}},
    )
    _check_equal(lazy, base)
    if lazy.exit_code == 0:
        _whole(seen)
        _check_intact(lazy)
    else:
        assert lazy.files == {} or set(lazy.files) == set(base.files)


def test_disqualifier_vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lazy, base, seen = _fallback_cell(
        monkeypatch,
        tmp_path,
        args=("--vault", "{out}/vault.db"),
        vault=True,
    )
    assert lazy.exit_code == 0, lazy.output
    _check_equal(lazy, base)
    _whole(seen)
    _check_intact(lazy)
