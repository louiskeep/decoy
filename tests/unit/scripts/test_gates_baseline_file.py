"""The stored failing-id baseline of `scripts/dev/gates.sh` (`--write-baseline`, `--baseline-file`).

A merge test runs the suite once and diffs its failing ids against a baseline written from a
clean origin/main. The baseline is only comparable while it is current and was written in the
same run mode, and a suite that quietly shrinks must not read as green.

Ported from the engine's test_gates_baseline_file.py (same cell names where the behavior is the
same, so the next port can diff them). CLI-only cells: the generated-svg staleness rule, the
SHA shape, the sentry-derived doc-walk guards, the memory-address refusal, copy-first and the
rewrite-between-check-and-copy cells. The promote contract and the guard on gates.sh itself are
in test_gates_legacy_verdict.py."""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from pathlib import Path

import pytest
from _gates_harness import (
    BASH,
    GIT,
    at_main,
    git,
    pytest_calls,
    recording_venv,
    seeded_clone,
)
from _gates_harness import gates as run_gates

pytestmark = pytest.mark.skipif(BASH is None or GIT is None, reason="needs bash and git")

WHOLE = ("--steps", "tests", "--full")
# Spelled out here, not taken from the reporter, so a wrong platform string in it shows up.
THIS_PLATFORM = f"{sys.platform}-{platform.machine()}"
NOT_A_COMMIT = "deadbeef" * 5


def _write(clone: Path, venv: Path, dest: Path, **env: str) -> tuple[int, str]:
    return run_gates(clone, venv, *WHOLE, "--write-baseline", str(dest), **env)


def _stored(tmp_path: Path, main_sha: str, **extra: object) -> Path:
    mode = {"workers": 1, "dist": "no", "platform": THIS_PLATFORM, "order": "collection"}
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
                "failing": ["tests/a.py::test_one", "tests/a.py::test_three"],
                **mode,
                "order_seconds": {},
                "file_seconds": {},
            }
            | extra
        )
    )
    return dest


def _compare(clone: Path, venv: Path, stored: Path, *args: str, **env: str) -> tuple[int, str]:
    return run_gates(clone, venv, *(args or WHOLE), "--baseline-file", str(stored), **env)


def _origin_main(clone: Path) -> str:
    return git(clone, "rev-parse", "origin/main").strip()


# --- AT-1, AT-2, AT-3: the write -------------------------------------------------------------


def test_full_flag_runs_the_whole_tests_directory(tmp_path: Path) -> None:
    clone = seeded_clone(tmp_path)
    venv, log = recording_venv(tmp_path)
    _rc, out = run_gates(clone, venv, "--steps", "ruff,tests", "--full")
    assert "full suite (tests)" in out, out
    calls = pytest_calls(log)
    assert len(calls) == 1 and calls[0][-1] == "tests", calls


@pytest.mark.parametrize(
    "args",
    [
        ["--steps", "tests", "tests/_seeded"],
        ["--steps", "tests"],
        ["--steps", "ruff", "--full"],
    ],
    ids=["explicit-paths", "changed-selection", "no-tests-step"],
)
def test_write_baseline_refuses_a_selection(tmp_path: Path, args: list[str]) -> None:
    clone = seeded_clone(tmp_path)
    at_main(clone)
    venv, log = recording_venv(tmp_path)
    dest = tmp_path / "base.json"
    rc, out = run_gates(clone, venv, "--write-baseline", str(dest), *args)
    assert rc == 2 and "selection, not the whole suite" in out, out
    assert not dest.exists() and pytest_calls(log) == []


@pytest.mark.parametrize(
    ("setup", "message"),
    [("seeded", "HEAD must equal origin/main"), ("dirty", "the tree must be clean")],
)
def test_write_baseline_refuses_a_head_that_is_not_a_clean_origin_main(
    tmp_path: Path, setup: str, message: str
) -> None:
    clone = seeded_clone(tmp_path)  # HEAD is one commit ahead of origin/main
    if setup == "dirty":
        at_main(clone)
        (clone / "stray.txt").write_text("x")
    venv, log = recording_venv(tmp_path)
    dest = tmp_path / "base.json"
    rc, out = _write(clone, venv, dest)
    assert rc == 2 and message in out, out
    assert not dest.exists() and pytest_calls(log) == []


def test_write_baseline_stores_the_failing_ids_and_the_run_mode(tmp_path: Path) -> None:
    clone = seeded_clone(tmp_path)
    main_sha = at_main(clone)
    venv, _log = recording_venv(tmp_path)
    dest = tmp_path / "base.json"
    rc, out = _write(
        clone, venv, dest, FAKE_FAIL="tests/b.py::test_two tests/a.py::test_one", FAKE_TOTAL="7"
    )
    assert rc == 1, out  # known failures still fail the plain run
    assert "gates: wrote baseline" in out, out
    assert json.loads(dest.read_text()) == {
        "format_version": 1,
        "repo": "decoy",
        "main_sha": main_sha,
        "head_sha": main_sha,
        "collected": 7,
        "skipped": 0,
        "failing": ["tests/a.py::test_one", "tests/b.py::test_two"],
        "workers": 1,
        "dist": "no",
        "platform": THIS_PLATFORM,
        "order": "collection",
        "order_seconds": {},
        "file_seconds": {"tests/a.py": 2.25, "tests/b.py": 1.0},
    }, out


def test_write_baseline_is_refused_when_an_earlier_step_stopped_the_run(tmp_path: Path) -> None:
    clone = seeded_clone(tmp_path)
    at_main(clone)
    venv, _log = recording_venv(tmp_path)
    (venv / "bin" / "ruff").write_text("#!/bin/sh\nexit 1\n")
    dest = tmp_path / "base.json"
    rc, out = run_gates(
        clone, venv, "--steps", "ruff,tests", "--full", "--write-baseline", str(dest)
    )
    assert rc != 0 and "did not finish the whole suite" in out, out
    assert not dest.exists()


@pytest.mark.parametrize("env", [{"PYTEST_ADDOPTS": "-k chosen"}, {"PYTEST_PLUGINS": "deselect"}])
def test_write_baseline_ignores_a_selection_smuggled_in_through_the_environment(
    tmp_path: Path, env: dict[str, str]
) -> None:
    clone = seeded_clone(tmp_path)
    at_main(clone)
    venv, log = recording_venv(tmp_path)
    dest = tmp_path / "base.json"
    rc, out = _write(clone, venv, dest, **env)
    assert rc == 0, out
    assert json.loads(dest.read_text())["collected"] == 5, out
    assert "-o addopts=" in log.read_text()


@pytest.mark.parametrize(
    ("env", "ids"),
    [
        ({"FAKE_FAIL": "tests/a.py::test_p[a - b]"}, ["tests/a.py::test_p[a - b]"]),
        (
            {"FAKE_FAIL": "tests/a.py::test_p[case] - main]|tests/a.py::test_p[case] - branch]"},
            ["tests/a.py::test_p[case] - branch]", "tests/a.py::test_p[case] - main]"],
        ),
        ({"FAKE_FAIL": "tests/a.py::test_one", "FAKE_NOISE": "1"}, ["tests/a.py::test_one"]),
        ({"FAKE_FAIL": "tests/a.py::test_one", "FAKE_ANSI": "1"}, ["tests/a.py::test_one"]),
        ({"FAKE_FAIL": "tests/a.py::test_one", "FAKE_TRAILER": "1"}, ["tests/a.py::test_one"]),
    ],
    ids=["dash-in-param", "ids-that-collide-in-the-summary", "noise-lines", "ansi", "trailer"],
)
def test_write_baseline_takes_ids_from_the_junit_not_from_log_text(
    tmp_path: Path, env: dict[str, str], ids: list[str]
) -> None:
    clone = seeded_clone(tmp_path)
    at_main(clone)
    venv, _log = recording_venv(tmp_path)
    dest = tmp_path / "base.json"
    _write(clone, venv, dest, **env)
    assert json.loads(dest.read_text())["failing"] == ids


def test_write_baseline_stores_the_skipped_count_and_turns_colour_off(tmp_path: Path) -> None:
    clone = seeded_clone(tmp_path)
    at_main(clone)
    venv, log = recording_venv(tmp_path)
    dest = tmp_path / "base.json"
    _write(clone, venv, dest, FAKE_SKIPPED="3", PY_COLORS="1")
    assert json.loads(dest.read_text())["skipped"] == 3
    assert "--color=no" in log.read_text()


# --- AT-20: ids that carry a per-run memory address are not stored ----------------------------


def test_write_baseline_refuses_an_id_with_a_default_repr_memory_address(tmp_path: Path) -> None:
    clone = seeded_clone(tmp_path)
    at_main(clone)
    venv, _log = recording_venv(tmp_path)
    dest = tmp_path / "base.json"
    bad = "tests/a.py::test_x[<Thing at 0x7f3a2b1c>]"
    rc, out = _write(clone, venv, dest, FAKE_FAIL=bad)
    assert rc == 1, out
    assert "write-baseline refused" in out and bad in out, out
    assert not dest.exists()


def test_write_baseline_accepts_a_literal_hex_parameter(tmp_path: Path) -> None:
    clone = seeded_clone(tmp_path)
    at_main(clone)
    venv, _log = recording_venv(tmp_path)
    dest = tmp_path / "base.json"
    _write(clone, venv, dest, FAKE_FAIL="tests/a.py::test_x[0xdeadbeef]")
    assert json.loads(dest.read_text())["failing"] == ["tests/a.py::test_x[0xdeadbeef]"]


# --- AT-4: the compare -----------------------------------------------------------------------


def test_baseline_file_reports_new_and_fixed_ids_and_blocks_on_a_new_one(tmp_path: Path) -> None:
    clone = seeded_clone(tmp_path)
    venv, log = recording_venv(tmp_path)
    rc, out = _compare(
        clone,
        venv,
        _stored(tmp_path, _origin_main(clone)),
        FAKE_FAIL="tests/a.py::test_one tests/a.py::test_two",
        FAKE_TOTAL="7",
    )
    assert rc == 1, out
    assert (
        "NEW-FAILING   tests/a.py::test_two" in out
        and "NEW-FAILING   tests/a.py::test_one" not in out
    )
    assert "NOW-PASSING   tests/a.py::test_three" in out, out
    assert "collected: baseline=5 branch=7 delta=+2" in out, out
    assert len(pytest_calls(log)) == 1, "origin/main must not be rerun"
    assert len(git(clone, "worktree", "list").splitlines()) == 1


def test_baseline_file_passes_when_only_known_ids_fail(tmp_path: Path) -> None:
    clone = seeded_clone(tmp_path)
    venv, _log = recording_venv(tmp_path)
    rc, out = _compare(
        clone, venv, _stored(tmp_path, _origin_main(clone)), FAKE_FAIL="tests/a.py::test_one"
    )
    assert rc == 0, out
    assert "NEW-FAILING" not in out and "WARNING:" not in out, out
    assert "(new=0 now-passing=1 known-still-failing=1)" in out, out


@pytest.mark.parametrize(
    ("args", "env"),
    [
        (list(WHOLE), {"FAKE_TOTAL": "0"}),
        (list(WHOLE), {"FAKE_NOJUNIT": "1"}),
        (["--steps", "ruff", "--full"], {}),
        (["--steps", "tests", "tests/_seeded"], {}),
    ],
    ids=["zero-test-junit", "missing-junit", "no-tests-step", "partial-selection"],
)
def test_baseline_file_fails_without_a_completed_whole_suite_run(
    tmp_path: Path, args: list[str], env: dict[str, str]
) -> None:
    clone = seeded_clone(tmp_path)
    venv, _log = recording_venv(tmp_path)
    rc, out = _compare(clone, venv, _stored(tmp_path, _origin_main(clone)), *args, **env)
    assert rc != 0, out
    assert "needs a completed whole-suite tests step" in out or "no step ran" in out, out


def test_baseline_file_selection_exits_one_not_zero(tmp_path: Path) -> None:
    clone = seeded_clone(tmp_path)
    venv, _log = recording_venv(tmp_path)
    stored = _stored(tmp_path, _origin_main(clone))
    rc, out = _compare(clone, venv, stored, "--steps", "tests", "tests/_seeded")
    assert rc == 1 and "needs a completed whole-suite tests step" in out, out


def test_baseline_file_fails_when_the_branch_skips_more_than_the_baseline(tmp_path: Path) -> None:
    clone = seeded_clone(tmp_path)
    venv, _log = recording_venv(tmp_path)
    rc, out = _compare(
        clone, venv, _stored(tmp_path, _origin_main(clone)),
        FAKE_FAIL="tests/a.py::test_one", FAKE_SKIPPED="2",
    )  # fmt: skip
    assert rc == 1 and "WARNING: branch skipped 2 tests, the baseline skipped 0" in out, out


def test_baseline_file_tells_apart_param_ids_that_differ_after_a_dash(tmp_path: Path) -> None:
    clone = seeded_clone(tmp_path)
    venv, _log = recording_venv(tmp_path)
    stored = _stored(tmp_path, _origin_main(clone), failing=["tests/a.py::test_p[case] - main]"])
    rc, out = _compare(clone, venv, stored, FAKE_FAIL="tests/a.py::test_p[case] - branch]")
    assert rc == 1 and "NEW-FAILING   tests/a.py::test_p[case] - branch]" in out, out


# --- AT-10: pytest's totals line must agree with the JUnit -----------------------------------


def test_write_baseline_refuses_when_pytest_totals_disagree_with_the_junit(tmp_path: Path) -> None:
    clone = seeded_clone(tmp_path)
    at_main(clone)
    venv, _log = recording_venv(tmp_path)
    dest = tmp_path / "base.json"
    rc, out = _write(
        clone,
        venv,
        dest,
        FAKE_FAIL="tests/a.py::test_one",
        FAKE_TOTALS="2 failed, 3 passed in 0.01s",
    )
    assert rc == 3 and "pytest printed 2 failed/error but the JUnit has 1" in out, out
    assert "refusing to store the baseline" in out and not dest.exists()


def test_write_baseline_refuses_a_zero_test_junit(tmp_path: Path) -> None:
    clone = seeded_clone(tmp_path)
    at_main(clone)
    venv, _log = recording_venv(tmp_path)
    dest = tmp_path / "base.json"
    rc, out = _write(clone, venv, dest, FAKE_TOTAL="0")
    assert rc != 0 and "collected > 0" in out, out
    assert not dest.exists()


def test_baseline_file_refuses_when_pytest_prints_no_totals_line(tmp_path: Path) -> None:
    clone = seeded_clone(tmp_path)
    venv, _log = recording_venv(tmp_path)
    rc, out = _compare(
        clone, venv, _stored(tmp_path, _origin_main(clone)),
        FAKE_FAIL="tests/a.py::test_one", FAKE_NOTOTALS="1",
    )  # fmt: skip
    assert rc == 3, out
    assert "pytest printed no totals line but the JUnit has 1" in out, out
    assert "refusing to compare against the baseline" in out and "disagrees with the JUnit" in out


# --- AT-6: a baseline is only compared with a run of the same mode ---------------------------


def test_a_baseline_written_by_gates_is_comparable_by_gates(tmp_path: Path) -> None:
    clone = seeded_clone(tmp_path)
    at_main(clone)
    venv, _log = recording_venv(tmp_path)
    dest = tmp_path / "base.json"
    _write(clone, venv, dest, FAKE_FAIL="tests/a.py::test_one")
    rc, out = _compare(clone, venv, dest, FAKE_FAIL="tests/a.py::test_one")
    assert rc == 0, out
    assert "workers=1" in out and "run mode:" in out, out


def _label(seconds: dict[str, float]) -> str:
    """The engine's order label for a map, spelled out so the CLI cannot drift from it silently."""
    canon = json.dumps(seconds, sort_keys=True, separators=(",", ":"))
    return "file-seconds:" + hashlib.sha256(canon.encode()).hexdigest()


_OTHER_PLATFORM = "darwin-arm64" if not THIS_PLATFORM.startswith("darwin") else "linux-x86_64"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("workers", 4),
        ("dist", "loadfile"),
        ("platform", _OTHER_PLATFORM),
        ("order", "from-a-map"),
    ],
)
def test_a_baseline_from_another_run_mode_is_refused_before_running(
    tmp_path: Path, field: str, value: object
) -> None:
    clone = seeded_clone(tmp_path)
    venv, log = recording_venv(tmp_path)
    stored = _stored(tmp_path, _origin_main(clone), **{field: value})
    rc, out = _compare(clone, venv, stored)
    assert rc == 2, out
    assert f"run mode differs in {field}" in out and "rewrite the baseline in this mode" in out, out
    assert str(value) in out and "baseline {" in out and "this run {" in out, out
    assert pytest_calls(log) == []


@pytest.mark.parametrize(
    ("order", "order_seconds"),
    [
        ("file-seconds:deadbeef", {}),
        ("collection", {"tests/a.py": 1.0}),
        (_label({"tests/a.py": 3.0}), {"tests/a.py": 3.0}),
    ],
    ids=["label-without-map", "map-without-label", "ordered-by-a-map"],
)
def test_a_baseline_that_is_not_in_collection_order_is_refused(
    tmp_path: Path, order: str, order_seconds: dict[str, float]
) -> None:
    clone = seeded_clone(tmp_path)
    venv, log = recording_venv(tmp_path)
    stored = _stored(tmp_path, _origin_main(clone), order=order, order_seconds=order_seconds)
    rc, out = _compare(clone, venv, stored, FAKE_FAIL="tests/a.py::test_one")
    assert rc == 2 and "run mode differs in order" in out, out
    assert pytest_calls(log) == []


def test_a_baseline_for_another_repo_is_refused(tmp_path: Path) -> None:
    clone = seeded_clone(tmp_path)
    venv, _log = recording_venv(tmp_path)
    rc, out = _compare(clone, venv, _stored(tmp_path, _origin_main(clone), repo="decoy-engine"))
    assert rc == 2 and "is for repo 'decoy-engine'" in out, out


# --- AT-7: the stored file is read through one strict model ----------------------------------


@pytest.mark.parametrize(
    ("drop", "message"),
    [
        ("workers", "no workers"),
        ("order_seconds", "no order_seconds"),
        ("file_seconds", "no file_seconds"),
        ("skipped", "no skipped"),
        ("collected", "no collected"),
        ("failing", "no failing"),
        ("main_sha", "no main_sha"),
        ("format_version", "has format_version None"),
    ],
)
def test_a_baseline_without_the_run_mode_fields_is_refused(
    tmp_path: Path, drop: str, message: str
) -> None:
    clone = seeded_clone(tmp_path)
    venv, _log = recording_venv(tmp_path)
    stored = _stored(tmp_path, _origin_main(clone))
    data = json.loads(stored.read_text())
    del data[drop]
    stored.write_text(json.dumps(data))
    rc, out = _compare(clone, venv, stored)
    assert rc == 2 and message in out, out


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("collected", True),
        ("collected", "5"),
        ("collected", -1),
        ("skipped", False),
        ("skipped", 0.5),
        ("failing", "tests/a.py::test_one"),
        ("failing", [1, 2]),
        ("failing", None),
        ("file_seconds", []),
        ("format_version", 2),
        ("format_version", True),
        ("format_version", "1"),
        ("workers", True),
        ("workers", 0),
        ("workers", 1.0),
        ("dist", 1),
        ("platform", None),
        ("order", 3),
        ("repo", None),
        ("order_seconds", {"tests/a.py": True}),
        ("order_seconds", {"tests/a.py": -1}),
        ("file_seconds", {"tests/a.py": "1"}),
        # D10: both SHA fields are exactly 40 lowercase hex characters
        ("main_sha", ""),
        ("main_sha", 7),
        ("main_sha", None),
        ("main_sha", "origin/main"),
        ("main_sha", "HEAD"),
        ("main_sha", "abc1234"),
        ("main_sha", "A" * 40),
        ("main_sha", "a" * 40 + "\n"),
        ("head_sha", 5),
        ("head_sha", "refs/heads/main"),
        ("head_sha", "abc1234"),
        ("head_sha", "B" * 40),
        ("head_sha", "b" * 40 + "\n"),
    ],
)
def test_a_baseline_with_a_wrongly_typed_or_shaped_field_is_refused(
    tmp_path: Path, field: str, value: object
) -> None:
    clone = seeded_clone(tmp_path)
    venv, log = recording_venv(tmp_path)
    stored = _stored(tmp_path, _origin_main(clone))
    data = json.loads(stored.read_text()) | {field: value}
    stored.write_text(json.dumps(data))
    rc, out = _compare(clone, venv, stored, FAKE_FAIL="tests/a.py::test_one")
    assert rc == 2 and "rewrite the baseline" in out, out
    assert pytest_calls(log) == []


def test_a_baseline_with_an_unknown_field_is_refused(tmp_path: Path) -> None:
    clone = seeded_clone(tmp_path)
    venv, _log = recording_venv(tmp_path)
    rc, out = _compare(clone, venv, _stored(tmp_path, _origin_main(clone), extra_field=1))
    assert rc == 2 and "unknown field(s) extra_field" in out, out


def test_a_corrupt_baseline_cannot_hide_lost_tests_or_a_skip_flood(tmp_path: Path) -> None:
    # JSON true read as workers=1 and false as collected=0, with a huge skipped count, once let
    # a smaller suite that skips more exit 0.
    clone = seeded_clone(tmp_path)
    venv, _log = recording_venv(tmp_path)
    stored = _stored(tmp_path, _origin_main(clone), workers=True, collected=False, skipped=999999)
    rc, out = _compare(
        clone, venv, stored, FAKE_FAIL="tests/a.py::test_one", FAKE_TOTAL="3", FAKE_SKIPPED="2"
    )
    assert rc == 2 and "wrong type" in out, out


def test_a_missing_baseline_file_is_refused(tmp_path: Path) -> None:
    clone = seeded_clone(tmp_path)
    venv, _log = recording_venv(tmp_path)
    rc, out = _compare(clone, venv, tmp_path / "absent.json")
    assert rc == 2 and "baseline file not found" in out, out


# --- a flag that needs a file refuses a missing operand ---------------------------------------


@pytest.mark.parametrize("flag", ["--baseline-file", "--write-baseline"])
@pytest.mark.parametrize("tail", [[], ["--full"]], ids=["end-of-args", "next-token-is-a-flag"])
def test_a_baseline_flag_without_its_file_operand_exits_2(
    tmp_path: Path, flag: str, tail: list[str]
) -> None:
    clone = seeded_clone(tmp_path)
    venv, log = recording_venv(tmp_path)
    rc, out = run_gates(clone, venv, "--steps", "tests", flag, *tail)
    assert rc == 2 and f"{flag} needs a file operand" in out, out
    assert pytest_calls(log) == []


def test_baseline_file_naming_an_empty_path_exits_2(tmp_path: Path) -> None:
    clone = seeded_clone(tmp_path)
    venv, _log = recording_venv(tmp_path)
    rc, out = run_gates(clone, venv, "--steps", "tests", "--full", "--baseline-file", "")
    assert rc == 2 and "needs a file operand" in out, out


# --- head_sha must be a commit with main_sha's tree (accidental mismatch, not forgery) --------


@pytest.mark.parametrize(
    ("kind", "message", "rc"),
    [
        ("absent", "is not in this repository", 2),
        ("other-tree", "does not have the tree of main_sha", 2),
        ("same-tree", "", 0),
    ],
)
def test_a_baseline_head_must_have_the_tree_of_its_main(
    tmp_path: Path, kind: str, message: str, rc: int
) -> None:
    clone = seeded_clone(tmp_path)
    main = at_main(clone)
    if kind == "absent":
        head = "1" * 40
    elif kind == "other-tree":
        (clone / "tests" / "_seeded" / "test_other.py").write_text("def test_o():\n    pass\n")
        git(clone, "add", "-A")
        git(clone, "commit", "-qm", "other tree")
        head = git(clone, "rev-parse", "HEAD").strip()
    else:
        git(clone, "commit", "--allow-empty", "-qm", "same tree")
        head = git(clone, "rev-parse", "HEAD").strip()
    venv, log = recording_venv(tmp_path)
    stored = _stored(tmp_path, main, head_sha=head)
    got, out = _compare(clone, venv, stored, FAKE_FAIL="tests/a.py::test_one")
    assert got == rc, out
    if rc == 2:
        assert message in out and head in out, out
        assert pytest_calls(log) == []


def test_a_baseline_with_an_unknown_main_still_reports_it_as_stale_not_as_a_bad_head(
    tmp_path: Path,
) -> None:
    # head_sha resolves and differs from the unknown main_sha, so the provenance branch that
    # leaves an unknown main to the staleness check is the one reached.
    clone = seeded_clone(tmp_path)
    venv, _log = recording_venv(tmp_path)
    stored = _stored(tmp_path, NOT_A_COMMIT, head_sha=_origin_main(clone))
    rc, out = _compare(clone, venv, stored)
    assert rc == 2 and "is stale against origin/main" in out, out
    assert f"stored main_sha {NOT_A_COMMIT} is not in this repository" in out, out
    assert "head_sha" not in out, out


def test_a_carry_shaped_baseline_is_accepted(tmp_path: Path) -> None:
    # A carried file moves main_sha and head_sha together to the new main, and the new main has
    # another tree than the run that produced the failing ids.
    clone = seeded_clone(tmp_path)
    at_main(clone)
    (clone / "tests" / "_seeded" / "test_moved.py").write_text("def test_m():\n    pass\n")
    git(clone, "add", "-A")
    git(clone, "commit", "-qm", "main moves")
    new_main = at_main(clone)
    venv, _log = recording_venv(tmp_path)
    stored = _stored(tmp_path, new_main, head_sha=new_main)
    rc, out = _compare(clone, venv, stored, FAKE_FAIL="tests/a.py::test_one")
    assert rc == 0, out


@pytest.mark.parametrize("flag", ["--steps"])
@pytest.mark.parametrize("tail", [[], ["--full"]], ids=["end-of-args", "next-token-is-a-flag"])
def test_steps_without_its_operand_exits_2(tmp_path: Path, flag: str, tail: list[str]) -> None:
    clone = seeded_clone(tmp_path)
    venv, log = recording_venv(tmp_path)
    rc, out = (
        run_gates(clone, venv, flag, *tail) if tail else run_gates(clone, venv, "--full", flag)
    )
    assert rc == 2 and f"{flag} needs a list of steps" in out, out
    assert pytest_calls(log) == []


def test_a_rename_of_a_test_file_into_markdown_makes_the_baseline_stale(tmp_path: Path) -> None:
    # With rename detection `git diff --name-only` lists only the new path, so a deleted test
    # moved to docs/*.md would read as a harmless Markdown add. No detection lists both paths.
    clone = seeded_clone(tmp_path)
    at_main(clone)
    venv, log = recording_venv(tmp_path)
    old = _origin_main(clone)
    (clone / "docs").mkdir(exist_ok=True)
    git(clone, "mv", "tests/_seeded/test_seed_ok.py", "docs/par-" + "renamed-probe.md")
    git(clone, "commit", "-qm", "rename into docs")
    at_main(clone)
    rc, out = _compare(clone, venv, _stored(tmp_path, old), FAKE_FAIL="tests/a.py::test_one")
    assert rc == 2 and "main changed tests/_seeded/test_seed_ok.py" in out, out
    assert pytest_calls(log) == []


# --- AT-5: a stored baseline is only compared while it is current ----------------------------


def _main_moves(clone: Path, files: dict[str, str]) -> str:
    """Move origin/main (and HEAD) forward by one commit; return the old main."""
    old = _origin_main(clone)
    for rel, body in files.items():
        (clone / rel).parent.mkdir(parents=True, exist_ok=True)
        (clone / rel).write_text(body)
    git(clone, "add", "-A")
    git(clone, "commit", "-qm", "main moves")
    at_main(clone)
    return old


def _stale_run(
    tmp_path: Path,
    files: dict[str, str],
    before: dict[str, str] | None = None,
    failing: list[str] | None = None,
    gates_edit: tuple[str, str] | None = None,
):
    clone = seeded_clone(tmp_path)
    if gates_edit:  # a seeded repo-config line, to reach a branch the CLI's own config leaves empty
        script = clone / "scripts" / "dev" / "gates.sh"
        text = script.read_text()
        assert text.count(gates_edit[0]) == 1, gates_edit
        script.write_text(text.replace(*gates_edit))
        git(clone, "add", "-A")
        git(clone, "commit", "-qm", "seed config")
    at_main(clone)  # the stored baseline is of this head, so only the moves below differ
    if before:  # files that exist on both sides, so a test can name them
        _main_moves(clone, before)
    venv, log = recording_venv(tmp_path)
    old = _main_moves(clone, files)
    extra = {"failing": failing} if failing else {}
    stored = _stored(tmp_path, old, **extra)
    rc, out = _compare(clone, venv, stored, FAKE_FAIL="tests/a.py::test_one")
    return rc, out, log


def test_a_baseline_behind_a_code_move_of_main_is_refused(tmp_path: Path) -> None:
    rc, out, log = _stale_run(tmp_path, {"src/decoy/_par_probe.py": "X = 1\n"})
    assert rc == 2 and "is stale against origin/main" in out and "rewrite it" in out, out
    assert pytest_calls(log) == []


def test_a_baseline_behind_an_unread_markdown_move_of_main_is_used(tmp_path: Path) -> None:
    # Built in two parts: this very file sits under tests/, so a literal name would be "named".
    rc, out, _log = _stale_run(tmp_path, {"docs/par-" + "unread-probe.md": "# x\n"})
    assert rc == 0, out
    assert "main moved only in Markdown or generated diagrams no test reads" in out, out


def test_a_baseline_behind_an_unread_generated_svg_is_used(tmp_path: Path) -> None:
    rc, out, _log = _stale_run(tmp_path, {"docs/diagrams/par-" + "unread-probe.svg": "<svg/>\n"})
    assert rc == 0, out
    assert "main moved only in Markdown or generated diagrams no test reads" in out, out


def test_a_baseline_behind_a_markdown_a_test_names_is_refused(tmp_path: Path) -> None:
    named = {"tests/_seeded/test_names_doc.py": "DOC = 'docs/par-named.md'\n"}
    rc, out, _log = _stale_run(tmp_path, {"docs/par-named.md": "# x\n"}, before=named)
    assert rc == 2 and "which a test names" in out, out


def test_a_baseline_behind_a_markdown_only_a_test_helper_names_is_refused(tmp_path: Path) -> None:
    helper = {"tests/_seeded/_names_doc.py": "DOC = 'docs/par-helper.md'\n"}
    rc, out, _log = _stale_run(tmp_path, {"docs/par-helper.md": "# x\n"}, before=helper)
    assert rc == 2 and "which a test names" in out, out


def test_a_baseline_behind_an_svg_a_test_names_is_refused(tmp_path: Path) -> None:
    named = {"tests/_seeded/test_names_svg.py": "SVG = 'docs/diagrams/par-named.svg'\n"}
    rc, out, _log = _stale_run(tmp_path, {"docs/diagrams/par-named.svg": "<svg/>\n"}, before=named)
    assert rc == 2 and "which a test names" in out, out


@pytest.mark.parametrize(
    "path",
    [
        "docs/conf.py",
        "docs/methodology-registry.yaml",
        "tests/_seeded/test_new.py",
        "docs/diagrams/par-notes.txt",
    ],
)
def test_a_baseline_behind_a_non_markdown_move_is_refused(tmp_path: Path, path: str) -> None:
    rc, out, _log = _stale_run(tmp_path, {path: "x = 1\n"})
    assert rc == 2 and "is stale against origin/main" in out, out


def test_a_baseline_behind_a_markdown_in_a_doc_walk_root_is_refused(tmp_path: Path) -> None:
    # The CLI walks no doc directory (DOC_WALK_ROOTS is empty), so the root is seeded.
    rc, out, _log = _stale_run(
        tmp_path,
        {"docs/walked/par-probe.md": "# x\n"},
        gates_edit=("DOC_WALK_ROOTS=()", "DOC_WALK_ROOTS=(docs/walked)"),
    )
    assert rc == 2 and "which a sentry walks" in out, out


def test_a_baseline_from_a_commit_this_repository_lacks_is_refused(tmp_path: Path) -> None:
    clone = seeded_clone(tmp_path)
    venv, _log = recording_venv(tmp_path)
    rc, out = _compare(clone, venv, _stored(tmp_path, NOT_A_COMMIT))
    assert rc == 2 and "is not in this repository" in out, out


@pytest.mark.parametrize(
    "walker",
    [
        "tests/sentry/test_baseline_registry.py::test_registry",
        "tests/sentry/test_some_future_docs_walker.py::test_x",
        "tests/unit/test_cli_surface.py::test_surface",
        "tests/unit/test_surface_docs_consistency.py::test_docs",
        "tests/unit/test_no_dead_command_strings.py::test_none",
    ],
)
def test_a_baseline_holding_a_sentry_failure_is_stale_after_any_move(
    tmp_path: Path, walker: str
) -> None:
    # A Markdown-only commit on main could fix this id and the branch re-break it, so the
    # docs-only exception does not apply while a sentry id is in the stored failing list. The
    # guard list is derived from SENTRY_PATHS: a directory entry and an exact file entry.
    clone = seeded_clone(tmp_path)
    at_main(clone)
    venv, log = recording_venv(tmp_path)
    old = _main_moves(clone, {"docs/par-" + "unread-probe.md": "# x\n"})
    stored = _stored(tmp_path, old, failing=["tests/a.py::test_one", walker])
    rc, out = _compare(clone, venv, stored, FAKE_FAIL="tests/a.py::test_one")
    assert rc == 2 and "sentry failure that a Markdown change on main could have hidden" in out, out
    assert pytest_calls(log) == []


# --- AT-8 and AT-9: a whole-suite run never shrinks silently ---------------------------------


def _shrink_clone(tmp_path: Path) -> Path:
    """origin/main holds test_gone.py; the branch commit is made by the caller."""
    clone = seeded_clone(tmp_path)
    (clone / "tests" / "_seeded" / "test_gone.py").write_text("def test_g():\n    pass\n")
    git(clone, "add", "-A")
    git(clone, "commit", "-qm", "gone exists")
    at_main(clone)
    return clone


def test_a_run_that_collects_ten_fewer_ids_than_the_baseline_fails(tmp_path: Path) -> None:
    clone = _shrink_clone(tmp_path)
    venv, _log = recording_venv(tmp_path)
    stored = _stored(tmp_path, _origin_main(clone), collected=15)
    rc, out = _compare(clone, venv, stored, FAKE_FAIL="tests/a.py::test_one", FAKE_TOTAL="5")
    assert rc == 1, out
    assert "collects 10 fewer tests than the baseline but deleted only 0" in out, out


def test_a_branch_that_deleted_the_test_file_holding_those_ids_passes(tmp_path: Path) -> None:
    clone = _shrink_clone(tmp_path)
    git(clone, "rm", "-q", "tests/_seeded/test_gone.py")
    git(clone, "commit", "-qm", "delete gone")
    venv, _log = recording_venv(tmp_path)
    stored = _stored(tmp_path, _origin_main(clone), collected=15)
    env = {"FAKE_FAIL": "tests/a.py::test_one", "FAKE_TOTAL": "5", "FAKE_COLLECT": "10"}
    rc, out = _compare(clone, venv, stored, **env)
    assert rc == 0, out
    assert "collected: baseline=15 branch=5 delta=-10" in out, out
    assert "collected 10 fewer tests than the baseline; the branch deleted 10" in out, out
    assert len(git(clone, "worktree", "list").splitlines()) == 1
    rc, out = _compare(clone, venv, stored, **env | {"FAKE_COLLECT": "9"})
    assert rc == 1 and "deleted only 9" in out, out
    assert len(git(clone, "worktree", "list").splitlines()) == 1


def test_a_renamed_test_file_is_not_a_deletion(tmp_path: Path) -> None:
    clone = _shrink_clone(tmp_path)
    git(clone, "mv", "tests/_seeded/test_gone.py", "tests/_seeded/test_moved.py")
    git(clone, "commit", "-qm", "rename gone")
    venv, _log = recording_venv(tmp_path)
    stored = _stored(tmp_path, _origin_main(clone), collected=15)
    env = {"FAKE_FAIL": "tests/a.py::test_one", "FAKE_TOTAL": "5", "FAKE_COLLECT": "10"}
    rc, out = _compare(clone, venv, stored, **env)
    assert rc == 1 and "deleted only 0" in out, out


def test_a_bigger_suite_than_the_baseline_is_not_a_shrink(tmp_path: Path) -> None:
    clone = seeded_clone(tmp_path)
    venv, _log = recording_venv(tmp_path)
    rc, out = _compare(
        clone, venv, _stored(tmp_path, _origin_main(clone)),
        FAKE_FAIL="tests/a.py::test_one", FAKE_TOTAL="9",
    )  # fmt: skip
    assert rc == 0, out


# --- AT-18a and AT-18b: the file that is checked is the file that is read --------------------


def _rewritten(tmp_path: Path, stored: Path, main_sha: str, failing: list[str]) -> Path:
    """A valid stored file, beside the real one, that already lists the id the run will fail with."""
    other = tmp_path / "rewrite-src.json"
    other.write_text(
        json.dumps(json.loads(stored.read_text()) | {"failing": failing, "main_sha": main_sha})
    )
    return other


def test_the_stored_file_is_copied_before_it_is_checked(tmp_path: Path) -> None:
    # The shim rewrites the original on the first --check-stored call, after the correct code has
    # copied it. A check-then-copy gate would copy the rewrite and call the new id known.
    clone = seeded_clone(tmp_path)
    venv, _log = recording_venv(tmp_path)
    stored = _stored(tmp_path, _origin_main(clone))
    new_id = "tests/a.py::test_seeded_new"
    src = _rewritten(tmp_path, stored, _origin_main(clone), ["tests/a.py::test_one", new_id])
    rc, out = _compare(
        clone, venv, stored,
        FAKE_FAIL=f"tests/a.py::test_one {new_id}",
        FAKE_CHECK_REWRITE_SRC=str(src), FAKE_CHECK_REWRITE_DST=str(stored),
    )  # fmt: skip
    assert json.loads(stored.read_text())["failing"] == ["tests/a.py::test_one", new_id], out
    assert rc == 1 and f"NEW-FAILING   {new_id}" in out, out


def test_the_stored_file_is_not_read_again_after_the_copy(tmp_path: Path) -> None:
    # The suite itself rewrites the original (adds its own id and moves main_sha). The verdict
    # must still come from the copy taken before the run.
    clone = seeded_clone(tmp_path)
    venv, _log = recording_venv(tmp_path)
    stored = _stored(tmp_path, _origin_main(clone))
    new_id = "tests/a.py::test_seeded_new"
    src = _rewritten(tmp_path, stored, NOT_A_COMMIT, ["tests/a.py::test_one", new_id])
    rc, out = _compare(
        clone, venv, stored,
        FAKE_FAIL=f"tests/a.py::test_one {new_id}",
        FAKE_REWRITE_SRC=str(src), FAKE_REWRITE_DST=str(stored),
    )  # fmt: skip
    assert json.loads(stored.read_text())["main_sha"] == NOT_A_COMMIT, out
    assert rc == 1 and f"NEW-FAILING   {new_id}" in out, out
