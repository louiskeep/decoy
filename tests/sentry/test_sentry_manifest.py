"""AT-CI1 and AT-CI2: the local gate's sentry step collects every sentry in ``SENTRIES``.

``scripts/dev/gates.sh`` runs ``SENTRY_PATHS`` with ``PYTEST_ARGS`` (which may carry a ``-m``
filter). A sentry outside those paths, or one a marker filter deselects, never runs at merge
time, so this test reads the same two settings from gates.sh and asks pytest what it would
collect.

Named limit: a module-level ``pytest.skip`` still collects, so a skipped sentry is not seen here.
"""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GATES = ROOT / "scripts" / "dev" / "gates.sh"

SENTRIES = (
    "tests/sentry/test_atomic_writer.py",
    "tests/sentry/test_bash32_compat.py",
    "tests/sentry/io_policy/test_layout_errors.py",
    "tests/sentry/io_policy/test_pipeline_argument.py",
    "tests/sentry/io_policy/test_output_placement.py",
    "tests/sentry/io_policy/test_private_files.py",
    "tests/sentry/io_policy/test_target_writes.py",
    "tests/sentry/cli_text/test_no_traceback_escape.py",
    "tests/sentry/cli_text/test_json_command_names.py",
    "tests/sentry/cli_text/test_user_text_internal_names.py",
    "tests/sentry/defects/test_anchored_regex.py",
    "tests/sentry/defects/test_config_error_routes.py",
    "tests/sentry/defects/test_exception_context.py",
    "tests/sentry/io_policy/test_csv_frame_choke_point.py",
    "tests/sentry/io_policy/test_small_file_reader.py",
    "tests/sentry/test_csv_read_choke_point.py",
    "tests/sentry/test_baseline_registry.py",
    "tests/sentry/test_ci_lock_installs.py",
    "tests/sentry/test_ci_output_isolation.py",
    "tests/sentry/test_ci_r2_leak_paths.py",
    "tests/sentry/test_engine_import_surface.py",
    "tests/sentry/test_engine_internal_boundary.py",
    "tests/sentry/test_engine_reason_code_copies.py",
    "tests/sentry/test_engine_secret_file_check.py",
    "tests/sentry/io_policy/test_fit_value_redaction.py",
    "tests/sentry/test_gate_single_entry.py",
    "tests/sentry/test_mask_secret_error_text.py",
    "tests/sentry/test_mask_secret_file_mode.py",
    "tests/sentry/test_mask_secret_ref_shape.py",
    "tests/sentry/test_notify_redaction.py",
    "tests/sentry/test_one_stderr_console.py",
    "tests/sentry/test_otel_closed.py",
    "tests/sentry/io_policy/test_profile_document_route.py",
    "tests/sentry/layout/test_codemap_paths.py",
    "tests/sentry/layout/test_run_package_shape.py",
    "tests/sentry/test_profile_raw_value_isolation.py",
    "tests/sentry/tooling/test_pytest_timeout.py",
    "tests/sentry/test_ratchet_check.py",
    "tests/sentry/test_report_raw_value_isolation.py",
    "tests/sentry/test_scan_reader.py",
    "tests/sentry/test_sentry_manifest.py",
    "tests/sentry/test_source_hygiene.py",
    "tests/sentry/test_yaml_error_leak_isolation.py",
    # Named sentries that live outside tests/sentry/.
    "tests/unit/test_cli_surface.py",
    "tests/unit/test_surface_docs_consistency.py",
    "tests/unit/test_no_dead_command_strings.py",
)


def _array(name: str, text: str) -> list[str] | None:
    m = re.search(rf"^{name}=\(([^)]*)\)", text, re.MULTILINE)
    return shlex.split(m.group(1), comments=True) if m else None


def gates_sentry_paths(text: str | None = None) -> list[str]:
    paths = _array("SENTRY_PATHS", GATES.read_text(encoding="utf-8") if text is None else text)
    assert paths is not None, "gates.sh has no SENTRY_PATHS array"
    return paths


def gates_marker_expr(text: str | None = None) -> str | None:
    """The ``-m`` expression in ``PYTEST_ARGS``, or None when the gate filters no marker."""
    args = _array("PYTEST_ARGS", GATES.read_text(encoding="utf-8") if text is None else text)
    assert args is not None, "gates.sh has no PYTEST_ARGS array"
    if "-m" not in args:
        return None
    i = args.index("-m")
    assert i + 1 < len(args), "PYTEST_ARGS has -m with no expression"
    return args[i + 1]


def uncovered(sentries: tuple[str, ...], paths: list[str]) -> list[str]:
    return [
        s for s in sentries if not any(s == p or s.startswith(p.rstrip("/") + "/") for p in paths)
    ]


def test_manifest_lists_every_sentry_file_and_no_ghost() -> None:
    on_disk = {
        p.relative_to(ROOT).as_posix() for p in (ROOT / "tests" / "sentry").glob("test_*.py")
    }
    listed = {s for s in SENTRIES if s.startswith("tests/sentry/")}
    assert on_disk - listed == set(), "sentry files missing from SENTRIES"
    assert [s for s in SENTRIES if not (ROOT / s).is_file()] == []
    assert len(set(SENTRIES)) == len(SENTRIES)


def test_gates_sentry_paths_cover_every_sentry() -> None:
    assert uncovered(SENTRIES, gates_sentry_paths()) == []


def test_removing_a_sentry_path_is_detected() -> None:
    """AT-CI2: dropping a path from SENTRY_PATHS makes the coverage check fail."""
    paths = gates_sentry_paths()
    assert paths, "SENTRY_PATHS is empty"
    for dropped in paths:
        rest = [p for p in paths if p != dropped]
        assert uncovered(SENTRIES, rest), f"dropping {dropped} went unnoticed"
    seeded = (*SENTRIES, "tests/policy/test_seeded.py")
    assert uncovered(seeded, paths) == ["tests/policy/test_seeded.py"]


def test_sentry_paths_parse_across_lines_and_comments() -> None:
    text = "X=1\nSENTRY_PATHS=(\n  tests/sentry  # dir\n  # whole-line comment\n  tests/u.py\n)\n"
    assert gates_sentry_paths(text) == ["tests/sentry", "tests/u.py"]


def test_marker_parse_handles_empty_and_present() -> None:
    assert gates_marker_expr("PYTEST_ARGS=()\n") is None
    assert gates_marker_expr("PYTEST_ARGS=(-m 'not slow')\n") == "not slow"


@pytest.fixture(scope="module")
def collected() -> set[str]:
    marker = gates_marker_expr()
    cmd = [
        sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider",
        *(("-m", marker) if marker is not None else ()), *gates_sentry_paths(),
    ]  # fmt: skip
    res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    assert res.returncode == 0, res.stdout[-2000:] + res.stderr[-2000:]
    return {line.split("::")[0] for line in res.stdout.splitlines() if "::" in line}


def test_gates_step_collects_every_sentry(collected: set[str]) -> None:
    assert [s for s in SENTRIES if s not in collected] == []
