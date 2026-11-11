"""AT-CI1 and AT-CI2: the local gate runs every sentry in ``SENTRIES`` exactly once.

``scripts/dev/gates.sh`` runs ``SENTRY_PATHS`` with ``PYTEST_ARGS`` (which may carry a ``-m``
filter). A sentry outside those paths, or one a marker filter deselects, never runs at merge
time, so this test reads the same settings from gates.sh and asks pytest what it would
collect. One sentry, ``LAYER_TEST``, is ignored by the sentry step and owned by the ``layers``
step, which runs it in its own venv (LAYOUT C3); the two routes must partition ``SENTRIES``
with no gap or overlap.

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
    "tests/sentry/ci_scan/test_identity.py",
    "tests/sentry/io_policy/test_layout_errors.py",
    "tests/sentry/io_policy/test_pipeline_argument.py",
    "tests/sentry/io_policy/test_output_placement.py",
    "tests/sentry/io_policy/test_private_files.py",
    "tests/sentry/io_policy/test_target_writes.py",
    "tests/sentry/io_policy/test_engine_base_dir.py",
    "tests/sentry/io_policy/test_private_files_aliases.py",
    "tests/sentry/io_policy/test_scaffold_publish.py",
    "tests/sentry/cli_text/test_help_panels.py",
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
    "tests/sentry/layout/test_import_layers.py",
    "tests/sentry/layout/test_module_size.py",
    "tests/sentry/layout/test_package_fanout.py",
    "tests/sentry/layout/test_run_package_shape.py",
    "tests/sentry/layout/test_vendored_files.py",
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


def gates_layer_test(text: str) -> str:
    m = re.search(r"^LAYER_TEST=(\S+)$", text, re.MULTILINE)
    assert m, "gates.sh has no LAYER_TEST"
    return m.group(1)


def gates_ignores(text: str) -> list[str]:
    """Every path ``LAYER_IGNORE`` excludes, with ``$LAYER_TEST`` resolved.

    The array goes through the same ``_array`` (shlex) parser as the other gate arrays, and both
    pytest spellings, ``--ignore=PATH`` and ``--ignore PATH``, count. Any other token is kept as
    it is, so it fails the route check instead of passing unseen.
    """
    layer = gates_layer_test(text)
    tokens = _array("LAYER_IGNORE", text)
    assert tokens is not None, "gates.sh has no LAYER_IGNORE array"
    paths: list[str] = []
    rest = iter(tokens)
    for token in rest:
        paths.append(next(rest, token) if token == "--ignore" else token.removeprefix("--ignore="))
    return [p.replace("$LAYER_TEST", layer) for p in paths]


def stray_ignores(text: str) -> int:
    """How many ``--ignore`` flags gates.sh has outside the ``LAYER_IGNORE`` array."""
    outside = re.sub(r"^LAYER_IGNORE=\([^)]*\)", "", text, flags=re.MULTILINE)
    return len(re.findall(r"--ignore\b", outside))


def route_findings(text: str) -> list[str]:
    """Why the ordinary and isolated sentry routes in ``text`` do not partition SENTRIES."""
    layer = gates_layer_test(text)
    found = []
    if layer not in SENTRIES:
        found.append(f"LAYER_TEST {layer} is not in SENTRIES")
    if gates_ignores(text) != [layer]:
        found.append(f"the only --ignore must be LAYER_TEST, got {gates_ignores(text)}")
    if stray_ignores(text):
        found.append("an --ignore outside LAYER_IGNORE hides tests from the route check")
    if not re.search(r"\bSTEPS=\S*\blayers\b", text):
        found.append("the default step list has no layers step")
    step = re.search(r"^\s+layers\) cmd=\(layer_step\b", text, re.MULTILINE)
    runs = re.search(
        r'^layer_step\(\) \{\n(?:.*\n)*?.*-m pytest "\$@" "\$LAYER_TEST"\n\}', text, re.MULTILINE
    )
    if not (step and runs):
        found.append("no layers step runs exactly $LAYER_TEST")
    if not re.search(r'\$\{LAYER_IGNORE\[@\]\+"\$\{LAYER_IGNORE\[@\]\}"\} \$\{SENTRY_PATHS', text):
        found.append("the sentry step does not apply LAYER_IGNORE")
    return found


def uncovered(sentries: tuple[str, ...], paths: list[str]) -> list[str]:
    return [
        s for s in sentries if not any(s == p or s.startswith(p.rstrip("/") + "/") for p in paths)
    ]


def sentry_files(root: Path) -> set[str]:
    """Every sentry test file under ``tests/sentry``, nested folders included."""
    return {p.relative_to(root).as_posix() for p in (root / "tests" / "sentry").rglob("test_*.py")}


def test_manifest_lists_every_sentry_file_and_no_ghost() -> None:
    on_disk = sentry_files(ROOT)
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


def test_ignore_parse_reads_both_spellings() -> None:
    head = "LAYER_TEST=tests/sentry/layout/test_import_layers.py\n"
    layer = "tests/sentry/layout/test_import_layers.py"
    assert gates_ignores(head + "LAYER_IGNORE=(--ignore=$LAYER_TEST)\n") == [layer]
    assert gates_ignores(head + "LAYER_IGNORE=(--ignore $LAYER_TEST)\n") == [layer]
    assert gates_ignores(head + "LAYER_IGNORE=(--ignore-glob=x)\n") == ["--ignore-glob=x"]


def test_marker_parse_handles_empty_and_present() -> None:
    assert gates_marker_expr("PYTEST_ARGS=()\n") is None
    assert gates_marker_expr("PYTEST_ARGS=(-m 'not slow')\n") == "not slow"


@pytest.fixture(scope="module")
def collected() -> set[str]:
    marker = gates_marker_expr()
    ignores = [f"--ignore={p}" for p in gates_ignores(GATES.read_text(encoding="utf-8"))]
    cmd = [
        sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider",
        *(("-m", marker) if marker is not None else ()), *ignores, *gates_sentry_paths(),
    ]  # fmt: skip
    res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    assert res.returncode == 0, res.stdout[-2000:] + res.stderr[-2000:]
    return {line.split("::")[0] for line in res.stdout.splitlines() if "::" in line}


def test_gates_step_collects_every_sentry(collected: set[str]) -> None:
    layer = gates_layer_test(GATES.read_text(encoding="utf-8"))
    assert [s for s in SENTRIES if s not in collected and s != layer] == []
    assert layer not in collected, "the sentry step must not run the layer test"


def test_the_sentry_and_layers_routes_partition_the_sentries() -> None:
    assert route_findings(GATES.read_text(encoding="utf-8")) == []


def test_a_broken_route_split_is_detected() -> None:
    """AT-8: removing the layers step or ignoring a second sentry is red."""
    text = GATES.read_text(encoding="utf-8")
    no_step = re.sub(r"^\s+layers\) cmd=\(layer_step.*\n", "", text, flags=re.MULTILINE)
    assert "no layers step runs exactly $LAYER_TEST" in route_findings(no_step)
    no_default = re.sub(r"(STEPS=\S*?),layers", r"\1", text)
    assert "the default step list has no layers step" in route_findings(no_default)
    second = text.replace(
        "LAYER_IGNORE=(--ignore=$LAYER_TEST)",
        "LAYER_IGNORE=(--ignore=$LAYER_TEST --ignore=tests/sentry/test_otel_closed.py)",
    )
    assert any("only --ignore" in f for f in route_findings(second))
    spaced = text.replace(
        "LAYER_IGNORE=(--ignore=$LAYER_TEST)",
        "LAYER_IGNORE=(--ignore $LAYER_TEST --ignore tests/sentry/test_otel_closed.py)",
    )
    assert any("only --ignore" in f for f in route_findings(spaced))
    stray = text.replace(
        "${SENTRY_PATHS", "--ignore tests/sentry/test_otel_closed.py ${SENTRY_PATHS"
    )
    assert any("outside LAYER_IGNORE" in f for f in route_findings(stray))
    unignored = text.replace(
        '${LAYER_IGNORE[@]+"${LAYER_IGNORE[@]}"} ${SENTRY_PATHS', "${SENTRY_PATHS"
    )
    assert "the sentry step does not apply LAYER_IGNORE" in route_findings(unignored)


def test_a_nested_unlisted_sentry_is_reported_missing(tmp_path: Path) -> None:
    """AT-8: the walk descends into sub-folders, so a planted nested sentry is not invisible."""
    nested = tmp_path / "tests" / "sentry" / "layout"
    nested.mkdir(parents=True)
    (nested / "test_unlisted.py").write_text("", encoding="utf-8")
    assert sentry_files(tmp_path) - set(SENTRIES) == {"tests/sentry/layout/test_unlisted.py"}
