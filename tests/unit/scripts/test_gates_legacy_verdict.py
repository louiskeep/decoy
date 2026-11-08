"""The legacy `--baseline` verdict, the plain-route pins and the contracts of gates.sh itself.

Legacy (declared changes C1 and C2): fail only on a branch-only step, and always keep going so
both sides ran every step. Plain route (pins): the CLI's own header wording, SKIP rules and
steps stay as they were. Contracts: the promote command line (`decoy-vm-t3-promote merged` runs a
copy of the reporter outside the repo) and the guard that keeps JSON and JUnit reading in the
reporter. The cells for the engine's `branch_only_steps` are ported from the engine's
test_dev_bootstrap_gates.py; the engine-only diagnostic and TESTS_REQUIRED cells are not (D2, D4)."""

from __future__ import annotations

import importlib.util
import json
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from _gates_harness import (
    BASH,
    DEV,
    GIT,
    at_main,
    git,
    pytest_argvs,
    pytest_calls,
    recording_venv,
    report_module,
    run,
    seeded_clone,
)
from _gates_harness import gates as run_gates

pytestmark = pytest.mark.skipif(BASH is None or GIT is None, reason="needs bash and git")


def _stored_file(tmp_path: Path, main_sha: str) -> Path:
    dest = tmp_path / "stored.json"
    dest.write_text(
        json.dumps(
            {
                "format_version": 1,
                "repo": "decoy",
                "main_sha": main_sha,
                "head_sha": main_sha,
                "collected": 5,
                "skipped": 0,
                "failing": [],
                "workers": 1,
                "dist": "no",
                "platform": f"{sys.platform}-{platform.machine()}",
                "order": "collection",
                "order_seconds": {},
                "file_seconds": {},
            }
        )
    )
    return dest


# --- AT-19: the legacy verdict ----------------------------------------------------------------


def test_gates_baseline_passes_when_the_only_failure_is_shared_with_main(tmp_path: Path) -> None:
    clone = seeded_clone(tmp_path)
    argv = [str(BASH), "scripts/dev/gates.sh", "--steps", "format,tests", "--baseline"]
    argv.append("tests/_seeded/test_seed_shared.py")
    proc = run(argv, clone)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    assert re.search(r"BOTH\s+tests/_seeded/test_seed_shared\.py::test_shared", out), out
    assert "(none)" in out.split("BRANCH-ONLY FAILING STEPS", 1)[-1], out


def test_gates_baseline_still_fails_on_a_branch_only_failure(tmp_path: Path) -> None:
    clone = seeded_clone(tmp_path)
    argv = [str(BASH), "scripts/dev/gates.sh", "--steps", "tests", "--baseline", "tests/_seeded"]
    proc = run(argv, clone)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 1, out
    assert "BRANCH-ONLY FAILING STEPS --\n  tests" in out, out


def test_baseline_mode_keeps_going_after_a_failing_step(tmp_path: Path) -> None:
    # No --keep-going: the failing ruff step must not stop either side from running its tests.
    clone = seeded_clone(tmp_path)
    venv, log = recording_venv(tmp_path)
    (venv / "bin" / "ruff").write_text("#!/bin/sh\necho 'boom'\nexit 1\n")
    rc, out = run_gates(
        clone, venv, "--steps", "ruff,tests", "--baseline", "tests/_seeded/test_seed_ok.py"
    )
    assert len(pytest_calls(log)) == 2, out  # branch and baseline both reached their tests step
    assert rc == 1, out  # default-format ruff output cannot be identified, so it fails closed


def _write_run(out: Path, label: str, rc: int, log: str, name: str = "mypy") -> None:
    with (out / f"{label}.steps").open("a") as fh:
        fh.write(f"{name}\t{rc}\t{name} src\n")
    (out / f"{label}-{name}.log").write_text(log)


_SHARED = 'src/a.py:62: error: Unused "type: ignore" comment  [unused-ignore]\n'


def _verdict(tmp_path: Path, branch: tuple[int, str], base: tuple[int, str]) -> list[str]:
    _write_run(tmp_path, "baseline", *base)
    _write_run(tmp_path, "branch", *branch)
    return report_module().branch_only_steps(tmp_path)


def test_a_branch_crash_is_branch_only_even_when_main_also_failed(tmp_path: Path) -> None:
    assert _verdict(tmp_path, (139, "Segmentation fault\n"), (1, _SHARED)) == ["mypy"]


@pytest.mark.parametrize("rc", [124, 137, 2])
def test_a_branch_timeout_is_branch_only_even_when_main_timed_out_too(
    tmp_path: Path, rc: int
) -> None:
    assert _verdict(tmp_path, (rc, ""), (rc, "")) == ["mypy"]


def test_a_failure_with_no_identifiable_diagnostic_is_branch_only(tmp_path: Path) -> None:
    assert _verdict(tmp_path, (1, "boom\n"), (1, _SHARED)) == ["mypy"]


def test_default_format_ruff_output_stays_branch_only(tmp_path: Path) -> None:
    # The CLI runs `ruff check` in its default format, which this reporter does not parse, so a
    # ruff failure never reads as shared with main. That is C1's fail-closed edge.
    ruff = "F401 [*] `os` imported but unused\n --> a.py:1:8\nFound 1 error.\n"
    assert _verdict(tmp_path, (1, ruff), (1, ruff)) == ["mypy"]


def test_a_duplicated_identical_diagnostic_is_branch_only(tmp_path: Path) -> None:
    twice = _SHARED + _SHARED.replace(":62:", ":90:")
    assert _verdict(tmp_path, (1, twice), (1, _SHARED)) == ["mypy"]


def test_identical_failures_on_both_sides_are_shared(tmp_path: Path) -> None:
    assert _verdict(tmp_path, (1, _SHARED.replace(":62:", ":70:")), (1, _SHARED)) == []


def test_a_total_that_disagrees_with_the_parsed_lines_is_branch_only(tmp_path: Path) -> None:
    log = _SHARED + "Found 2 errors in 1 file (checked 3 source files)\n"
    assert _verdict(tmp_path, (1, log), (1, _SHARED)) == ["mypy"]


def _write_pytest(
    out: Path, label: str, ids: list[str], declared: int | None = None, name: str = "tests"
) -> None:
    with (out / f"{label}.steps").open("a") as fh:
        fh.write(f"{name}\t1\tpytest\n")
    cases = "".join(
        f'<testcase classname="{i.split("::")[0]}" name="{i.split("::")[1]}"><failure/></testcase>'
        for i in ids
    )
    n = len(ids) if declared is None else declared
    (out / f"{label}-{name}.xml").write_text(
        f'<testsuite failures="{n}" errors="0">{cases}</testsuite>'
    )
    (out / f"{label}-{name}.log").write_text("".join(f"FAILED {i} - boom\n" for i in ids))


@pytest.mark.parametrize("step", ["tests", "sentry"])
def test_a_shared_pytest_failure_is_not_branch_only(tmp_path: Path, step: str) -> None:
    _write_pytest(tmp_path, "baseline", ["tests/test_a.py::test_old"], name=step)
    _write_pytest(tmp_path, "branch", ["tests/test_a.py::test_old"], name=step)
    assert report_module().branch_only_steps(tmp_path) == []


@pytest.mark.parametrize("step", ["tests", "sentry"])
def test_a_pytest_failure_main_lacks_is_branch_only_when_main_also_fails(
    tmp_path: Path, step: str
) -> None:
    _write_pytest(tmp_path, "baseline", ["tests/test_a.py::test_old"], name=step)
    _write_pytest(
        tmp_path, "branch", ["tests/test_a.py::test_old", "tests/test_b.py::test_new"], name=step
    )
    assert report_module().branch_only_steps(tmp_path) == [step]


def test_a_repeated_pytest_failure_counts_each_time(tmp_path: Path) -> None:
    _write_pytest(tmp_path, "baseline", ["tests/test_a.py::test_p"])
    _write_pytest(tmp_path, "branch", ["tests/test_a.py::test_p", "tests/test_a.py::test_p"])
    assert report_module().branch_only_steps(tmp_path) == ["tests"]


def test_a_junit_report_whose_totals_disagree_is_branch_only(tmp_path: Path) -> None:
    _write_pytest(tmp_path, "baseline", ["tests/test_a.py::test_old"])
    _write_pytest(tmp_path, "branch", ["tests/test_a.py::test_old"], declared=2)
    assert report_module().branch_only_steps(tmp_path) == ["tests"]


def test_a_branch_step_that_never_ran_is_branch_only(tmp_path: Path) -> None:
    _write_run(tmp_path, "baseline", 1, _SHARED + "Found 1 error in 1 file\n")
    _write_run(tmp_path, "branch", 1, _SHARED + "Found 1 error in 1 file\n")
    for label, row in (("baseline", "tests\t0\tpytest\n"), ("branch", "tests\t-2\t(not run)\n")):
        with (tmp_path / f"{label}.steps").open("a") as fh:
            fh.write(row)
    assert report_module().branch_only_steps(tmp_path) == ["tests"]


# --- AT-17: the plain route keeps the CLI's steps and wording ---------------------------------


def test_the_header_keeps_the_cli_skip_steps_and_selection_wording(tmp_path: Path) -> None:
    clone = seeded_clone(tmp_path)
    venv, _log = recording_venv(tmp_path)
    rc, out = run_gates(clone, venv, "--steps", "ruff,format,mypy,tests")
    assert "test paths: changed vs origin/main: 1 test file(s)" in out, out
    assert "[format] SKIP" in out and "$ (no format gate in ci.yml)" in out, out
    assert "[mypy] SKIP" in out and "$ (no mypy gate in ci.yml)" in out, out
    assert rc == 0, out


def test_the_header_names_the_serial_suite(tmp_path: Path) -> None:
    clone = seeded_clone(tmp_path)
    venv, _log = recording_venv(tmp_path)
    _rc, out = run_gates(clone, venv, "--steps", "tests", "tests/_seeded/test_seed_ok.py")
    assert "workers:    1 (the CLI suite runs serial)" in out, out


def test_an_explicit_path_keeps_the_explicit_wording(tmp_path: Path) -> None:
    clone = seeded_clone(tmp_path)
    venv, _log = recording_venv(tmp_path)
    _rc, out = run_gates(clone, venv, "--steps", "tests", "tests/_seeded/test_seed_ok.py")
    assert "test paths: explicit: tests/_seeded/test_seed_ok.py" in out, out


def test_the_sentry_step_runs_the_ratchet_first_and_then_the_four_sentry_paths(
    tmp_path: Path,
) -> None:
    clone = seeded_clone(tmp_path)
    venv, log = recording_venv(tmp_path)
    _rc, out = run_gates(clone, venv, "--steps", "sentry")
    shown = next(ln for ln in out.splitlines() if ln.lstrip().startswith("$ bash -c"))
    assert shown.index("ratchet_check.py") < shown.index("-m\\ pytest"), shown
    (argv,) = pytest_argvs(log)
    assert argv[-4:] == [
        "tests/sentry",
        "tests/unit/test_cli_surface.py",
        "tests/unit/test_surface_docs_consistency.py",
        "tests/unit/test_no_dead_command_strings.py",
    ], argv


def test_the_header_says_workers_stay_one_whatever_the_environment_asks(tmp_path: Path) -> None:
    clone = seeded_clone(tmp_path)
    venv, _log = recording_venv(tmp_path)
    _rc, out = run_gates(
        clone, venv, "--steps", "tests", "tests/_seeded/test_seed_ok.py", GATES_WORKERS="4"
    )
    assert "workers:    1 (the CLI suite runs serial)" in out, out


def test_order_from_is_not_a_cli_flag(tmp_path: Path) -> None:
    clone = seeded_clone(tmp_path)
    venv, _log = recording_venv(tmp_path)
    rc, out = run_gates(clone, venv, "--order-from", "x.json", "--steps", "tests")
    assert rc == 2 and "unknown flag --order-from" in out, out


def test_help_prints_the_whole_header_comment() -> None:
    proc = subprocess.run(
        [str(BASH), "scripts/dev/gates.sh", "--help"],
        cwd=DEV.parents[1], capture_output=True, text=True, timeout=60, check=False,
    )  # fmt: skip
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.rstrip().endswith("Use --full (or `tests`)."), proc.stdout


# --- AT-13: the promote contract --------------------------------------------------------------

_INHERITED_JUNIT = (
    '<testsuite tests="2" failures="1" errors="0" skipped="0">'
    '<testcase classname="tests.test_child.TestChild" name="test_inherited" '
    'file="tests/_base.py" time="2.0"><failure/></testcase>'
    '<testcase classname="tests.test_child.TestChild" name="test_own" '
    'file="tests/test_child.py" time="1.0"/>'
    "</testsuite>"
)


def _promote_inputs(tmp_path: Path) -> tuple[Path, Path, str]:
    """A clone and the output directory of a finished whole-suite run in it."""
    clone = seeded_clone(tmp_path)
    sha = at_main(clone)
    venv, _log = recording_venv(tmp_path)
    _rc, out = run_gates(clone, venv, "--steps", "tests", "--full")
    logs = Path(re.search(r"(?m)^logs:\s+(\S+)$", out).group(1))  # type: ignore[union-attr]
    (clone / "tests" / "_base.py").write_text("")
    (clone / "tests" / "test_child.py").write_text("")
    (logs / "branch-tests.xml").write_text(_INHERITED_JUNIT)
    (logs / "branch-tests.log").write_text("1 failed, 1 passed in 0.01s\n")
    return clone, logs, sha


def _reporter_write(
    reporter: Path, logs: Path, dest: Path, sha: str, *extra: str, head: str | None = None
):
    return subprocess.run(
        [sys.executable, str(reporter), str(logs), "--whole-suite", "--write-baseline", str(dest),
         "--repo", "decoy", "--main-sha", sha, f"--head-sha={head or sha}", *extra],
        capture_output=True, text=True, timeout=120, check=False,
    )  # fmt: skip


def test_a_reporter_copied_outside_the_repo_writes_the_same_file_as_a_gates_run(
    tmp_path: Path,
) -> None:
    clone, logs, sha = _promote_inputs(tmp_path)
    inside = tmp_path / "inside.json"
    done = _reporter_write(clone / "scripts" / "dev" / "_gates_report.py", logs, inside, sha)
    assert done.returncode == 0, done.stderr
    outside_dir = tmp_path / "promote"
    outside_dir.mkdir()
    for sibling in DEV.glob("_gates_*.py"):
        shutil.copy(sibling, outside_dir / sibling.name)
    copied = outside_dir / "_gates_report.py"
    outside = tmp_path / "outside.json"
    done = _reporter_write(copied, logs, outside, sha, "--test-root", str(clone))
    assert done.returncode == 0, done.stderr
    assert outside.read_text() == inside.read_text()
    assert json.loads(outside.read_text())["failing"] == [
        "tests/test_child.py::TestChild::test_inherited"
    ]
    # promote's reader check imports the model from the copied reporter by this name
    spec = importlib.util.spec_from_file_location("_promote_reporter", copied)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    assert "load_baseline" in mod.__all__
    assert mod.load_baseline(outside).failing == ("tests/test_child.py::TestChild::test_inherited",)


def test_a_reporter_copied_outside_the_repo_without_a_test_root_writes_nothing(
    tmp_path: Path,
) -> None:
    # Control for the cell above: outside the repo the commit cannot be resolved, so the write is
    # refused instead of keying inherited tests by the wrong root.
    _clone, logs, sha = _promote_inputs(tmp_path)
    outside_dir = tmp_path / "promote"
    outside_dir.mkdir()
    for sibling in DEV.glob("_gates_*.py"):
        shutil.copy(sibling, outside_dir / sibling.name)
    dest = tmp_path / "no-root.json"
    done = _reporter_write(outside_dir / "_gates_report.py", logs, dest, sha)
    assert done.returncode == 1 and "write-baseline refused" in done.stderr, done.stderr
    assert "is not in this repository" in done.stderr, done.stderr
    assert not dest.exists()


def test_a_write_whose_head_has_another_tree_than_main_is_refused(tmp_path: Path) -> None:
    clone, logs, sha = _promote_inputs(tmp_path)
    (clone / "tests" / "_seeded" / "test_other.py").write_text("def test_o():\n    pass\n")
    git(clone, "add", "-A")
    git(clone, "commit", "-qm", "other tree")
    head = git(clone, "rev-parse", "HEAD").strip()
    dest = tmp_path / "mismatch.json"
    reporter = clone / "scripts" / "dev" / "_gates_report.py"
    done = _reporter_write(reporter, logs, dest, sha, head=head)
    assert done.returncode == 1, done.stderr
    assert "write-baseline refused" in done.stderr and "does not have the tree" in done.stderr
    assert not dest.exists()


def test_a_write_naming_a_commit_the_repo_lacks_is_refused(tmp_path: Path) -> None:
    clone, logs, _sha = _promote_inputs(tmp_path)
    dest = tmp_path / "unknown.json"
    reporter = clone / "scripts" / "dev" / "_gates_report.py"
    done = _reporter_write(reporter, logs, dest, "2" * 40)
    assert done.returncode == 1 and "write-baseline refused" in done.stderr, done.stderr
    assert not dest.exists()


@pytest.mark.parametrize("head", ["abc1234", "A" * 40, "-" + "a" * 39])
def test_a_write_with_a_malformed_sha_is_refused_before_any_lookup(
    tmp_path: Path, head: str
) -> None:
    clone, logs, sha = _promote_inputs(tmp_path)
    dest = tmp_path / "shape.json"
    reporter = clone / "scripts" / "dev" / "_gates_report.py"
    done = _reporter_write(reporter, logs, dest, sha, head=head)
    assert done.returncode == 1 and "is not a full 40-character lowercase SHA" in done.stderr
    assert not dest.exists()


def test_the_unreadable_json_error_carries_no_exception_context(tmp_path: Path) -> None:
    # The parser's message can quote the stored text, so neither __cause__ nor __context__ may
    # hold it; `from None` alone leaves __context__ set.
    bad = tmp_path / "bad.json"
    bad.write_text("{ not json")
    mod = report_module()
    with pytest.raises(mod.BaselineError) as caught:
        mod.load_baseline(bad)
    assert caught.value.__cause__ is None and caught.value.__context__ is None


def test_a_refused_write_carries_no_exception_context(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "commit", "--allow-empty", "-qm", "one")
    sha = git(repo, "rev-parse", "HEAD").strip()
    mod = report_module()
    bad = mod.Baseline(
        repo="decoy", main_sha=sha, head_sha=sha, collected=1, skipped=0, failing=(),
        workers=0, dist="no", platform="x", order="collection", order_seconds={}, file_seconds={},
    )  # fmt: skip
    with pytest.raises(mod.WriteRefused) as caught:
        mod.store_baseline(tmp_path / "out.json", bad, repo)
    assert caught.value.__cause__ is None and caught.value.__context__ is None
    assert not (tmp_path / "out.json").exists()


@pytest.mark.parametrize("kind", ["missing", "regular-file"])
def test_a_test_root_that_is_not_a_directory_exits_64_and_writes_nothing(
    tmp_path: Path, kind: str
) -> None:
    clone, logs, sha = _promote_inputs(tmp_path)
    root = tmp_path / "absent" if kind == "missing" else clone / "tests" / "_base.py"
    dest = tmp_path / "refused.json"
    done = _reporter_write(clone / "scripts" / "dev" / "_gates_report.py", logs, dest, sha,
                           "--test-root", str(root))  # fmt: skip
    assert done.returncode == 64, done.stderr
    assert not dest.exists()


# --- AT-16: only the reporter reads JSON and JUnit --------------------------------------------

_ALLOWED_PY_ARGS = (
    ("-m", "pytest"),
    ("--version",),
    ("]",),  # `[ -x "$BIN/python" ]` existence test
    ("$ROOT/scripts/dev/_gates_report.py",),
    ('${junit[@]+"${junit[@]}"}',),  # args for the `bash -c` wrapper, built by gates.sh itself
)


def gates_sh_violations(text: str) -> list[str]:
    """Reasons gates.sh could read the stored file or JUnit outside _gates_report.py.

    By construction: every python call must run the reporter, `-m pytest` or `--version`.
    Any inline program (-c), stdin program (-), heredoc python, aliasing of the interpreter
    or jq is refused, so a renamed json import cannot slip past a substring list.
    """
    bad: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#"):
            continue
        if re.search(r"(^|[^\w])jq(\s|$)", line):
            bad.append(f"jq: {line}")
        if "python" not in line:
            continue
        if "<<" in line:
            bad.append(f"heredoc python: {line}")
        if re.search(r"^(export\s+|local\s+)?\w+=[\"']?[^\s\"'()]*python", line):
            bad.append(f"python aliased: {line}")
        for m in re.finditer(r'(?<![\w-])python[\d.]*(?![\w:])"?([^\n]*)', line):
            args = tuple(t.strip(')"') for t in m.group(1).split()[:2])
            if args and not any(args[: len(a)] == a for a in _ALLOWED_PY_ARGS):
                bad.append(f"python runs something else: {line}")
    return bad


def test_gates_sh_runs_python_only_through_allow_listed_programs() -> None:
    assert gates_sh_violations((DEV / "gates.sh").read_text()) == []


@pytest.mark.parametrize(
    "line",
    [
        '"$BIN/python" -c \'from json import load; print(load(open("baseline.json")))\'',
        '"$BIN/python" -c \'import json as j; j.load(open("b"))\'',
        '"$BIN/python" -c \'__import__("json").load(open("b"))\'',
        '"$BIN/python" - <<EOF',
        '"$BIN/python" - < prog.py',
        "PY=$BIN/python",
        'jq .main_sha "$BASEFILE"',
        "x=$(echo '{}' | jq -r .a)",
    ],
)
def test_the_gates_sh_guard_refuses_each_seeded_reader(line: str) -> None:
    assert gates_sh_violations("set -e\n" + line + "\n"), line


# --- the reporter against real pytest output --------------------------------------------------


def test_junit_ids_from_a_real_pytest_run_keep_params_classes_and_errors(tmp_path: Path) -> None:
    src = tmp_path / "proj" / "tests" / "sub"
    src.mkdir(parents=True)
    (src / "test_x.py").write_text(
        "import pytest\n"
        '@pytest.mark.parametrize("v", ["case] - main", "case] - branch", "x::y"])\n'
        "def test_p(v): assert False\n"
        "class TestA:\n"
        "    def test_m(self): assert False\n"
        "    class TestInner:\n"
        "        def test_n(self): assert False\n"
        "@pytest.fixture\n"
        "def boom(): raise RuntimeError\n"
        "def test_setup_err(boom): pass\n"
    )
    (src.parent / "test_coll.py").write_text("import nothing_here_at_all\n")
    xml = tmp_path / "o.xml"
    subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "junit_family=xunit1",
         "--continue-on-collection-errors", f"--junitxml={xml}", "tests"],
        cwd=tmp_path / "proj", capture_output=True, text=True, timeout=120, check=False,
    )  # fmt: skip
    out = tmp_path / "out"
    out.mkdir()
    shutil.copy(xml, out / "branch-tests.xml")
    f = "tests/sub/test_x.py"
    assert sorted(report_module().junit_failing_ids(out, "branch")) == sorted(
        [
            f"{f}::test_p[case] - main]",
            f"{f}::test_p[case] - branch]",
            f"{f}::test_p[x::y]",
            f"{f}::TestA::test_m",
            f"{f}::TestA::TestInner::test_n",
            f"{f}::test_setup_err",
            "tests/test_coll.py",
        ]
    )


def test_totals_count_matches_the_junit_on_a_real_run_with_teardown_errors(tmp_path: Path) -> None:
    proj = tmp_path / "proj"
    (proj / "tests").mkdir(parents=True)
    (proj / "tests" / "test_t.py").write_text(
        "import pytest\n"
        "@pytest.fixture\n"
        "def td():\n"
        "    yield\n"
        "    raise RuntimeError\n"
        "def test_fail_and_teardown(td): assert False\n"
        "def test_pass_but_teardown(td): pass\n"
    )
    out = tmp_path / "out"
    out.mkdir()
    run = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "junit_family=xunit1",
         f"--junitxml={out / 'branch-tests.xml'}", "tests"],
        cwd=proj, capture_output=True, text=True, timeout=120, check=False,
    )  # fmt: skip
    (out / "branch-tests.log").write_text(run.stdout)
    mod = report_module()
    assert mod.pytest_totals_failed(out, "branch") == 3, run.stdout
    assert mod.junit_failure_elements(out, "branch") == 3


def test_the_reporter_names_the_file_it_seconds_by(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "branch-tests.xml").write_text(
        '<testsuite tests="3" failures="0" errors="0" skipped="0">'
        '<testcase classname="t.a" name="x" file="t/a.py" time="1.5"/>'
        '<testcase classname="t.a" name="y" file="t/a.py" time="0.5"/>'
        '<testcase classname="t.b" name="z" file="t/b.py" time="0.25"/>'
        "</testsuite>"
    )
    assert report_module().file_seconds(out, "branch") == {"t/a.py": 2.0, "t/b.py": 0.25}


def test_reporter_subcommands_replace_the_inline_parsing(tmp_path: Path) -> None:
    mod = Path(report_module().__file__)
    out = tmp_path / "out"
    out.mkdir()
    (out / "branch-tests.xml").write_text("<testsuite")  # truncated
    zero = subprocess.run(
        [sys.executable, str(mod), "--suite-collected", str(out)],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert zero.stdout.strip() == "0"
    (out / "branch-tests.xml").write_text(
        '<testsuite tests="3" failures="0" errors="0" skipped="0"/>'
    )
    three = subprocess.run(
        [sys.executable, str(mod), "--suite-collected", str(out)],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert three.stdout.strip() == "3"
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "commit", "--allow-empty", "-qm", "one")
    sha = git(repo, "rev-parse", "HEAD").strip()
    stored = _stored_file(tmp_path, sha)
    shown = subprocess.run(
        [sys.executable, str(mod), "--check-stored", str(stored), "decoy", "1", str(repo)],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert shown.returncode == 0 and shown.stdout.strip() == sha
    workers = subprocess.run(
        [sys.executable, str(mod), "--workers"], capture_output=True, text=True, check=False
    )  # fmt: skip
    assert workers.returncode == 0 and workers.stdout.strip() == "1 the CLI suite runs serial"


# --- AT-12: an inherited test is keyed by the collected module -------------------------------

_INHERITED_JUNIT = (
    '<testsuite tests="2" failures="1" errors="0" skipped="0">'
    '<testcase classname="tests.test_child.TestChild" name="test_inherited" '
    'file="tests/_base.py" time="2.0"><failure/></testcase>'
    '<testcase classname="tests.test_child.TestChild" name="test_own" '
    'file="tests/test_child.py" time="1.0"/>'
    "</testsuite>"
)


def test_an_inherited_test_is_keyed_by_the_collected_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "proj"
    (root / "tests").mkdir(parents=True)
    (root / "tests" / "_base.py").write_text("")
    (root / "tests" / "test_child.py").write_text("")
    out = tmp_path / "out"
    out.mkdir()
    (out / "branch-tests.xml").write_text(_INHERITED_JUNIT)
    mod = report_module()
    monkeypatch.setattr(mod, "TEST_ROOT", root)
    assert mod.junit_failing_ids(out, "branch") == [
        "tests/test_child.py::TestChild::test_inherited"
    ]
    assert mod.file_seconds(out, "branch") == {"tests/test_child.py": 3.0}


def test_an_inherited_test_from_a_real_run_has_a_rerunnable_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proj = tmp_path / "proj"
    (proj / "tests").mkdir(parents=True)
    (proj / "tests" / "__init__.py").write_text("")
    (proj / "tests" / "_base.py").write_text(
        "class Contract:\n    def test_inherited(self): assert False\n"
    )
    (proj / "tests" / "test_child.py").write_text(
        "from tests._base import Contract\nclass TestChild(Contract):\n    pass\n"
    )
    xml = tmp_path / "o.xml"
    subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "junit_family=xunit1",
         f"--junitxml={xml}", "tests/test_child.py"],
        cwd=proj, capture_output=True, text=True, timeout=120, check=False,
    )  # fmt: skip
    out = tmp_path / "out"
    out.mkdir()
    shutil.copy(xml, out / "branch-tests.xml")
    mod = report_module()
    monkeypatch.setattr(mod, "TEST_ROOT", proj)
    assert mod.junit_failing_ids(out, "branch") == [
        "tests/test_child.py::TestChild::test_inherited"
    ]
    assert set(mod.file_seconds(out, "branch")) == {"tests/test_child.py"}
