"""A7: the staged scan reads the Git INDEX (stage 0 blobs by object id), never the worktree.

Every test uses a real temporary Git repository and the real `decoy` process.
"""

from __future__ import annotations

import os
import shutil
import stat
import time
import urllib.parse
from pathlib import Path

import pytest

from decoy.cli.exit_codes import EXIT_FINDINGS, EXIT_OK, EXIT_RUNTIME, EXIT_USAGE
from tests.ci_support import (
    MANIFEST_NAME,
    ci_check,
    ci_manifest,
    commit_all,
    git,
    make_repo,
    parse_stdout,
    write,
)

LITERAL = "DECOY_TEST_IDENTIFIER_"
PATTERN = {"id": "pii.seeded-test-identifier", "literal": LITERAL, "paths": ["fixtures/**"]}
RULE = "staged.pii.seeded-test-identifier"


def _repo(tmp_path: Path, manifest: str | None = None) -> Path:
    repo = make_repo(tmp_path / "repo")
    write(repo, MANIFEST_NAME, manifest or ci_manifest(validation=False, patterns=[PATTERN]))
    write(repo, "README.md", "base\n")
    commit_all(repo)
    return repo


def _scan(repo: Path, *extra: str, env: dict[str, str] | None = None):
    proc = ci_check(repo, "--format", "json", *extra, env=env)
    return proc, parse_stdout(proc)


def _paths(report: dict) -> list[str]:
    return [urllib.parse.unquote(f["location"]["uri"]) for f in report["findings"]]


def test_staged_canary_blocks_even_when_the_worktree_is_clean(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    write(repo, "fixtures/a.txt", f"one\ntwo\n  {LITERAL}42\n")
    git(repo, "add", "fixtures/a.txt")
    write(repo, "fixtures/a.txt", "clean worktree\n")
    proc, report = _scan(repo)
    assert proc.returncode == EXIT_FINDINGS, proc.stderr
    (f,) = report["findings"]
    assert f["rule_id"] == RULE and f["location"]["uri"] == "fixtures/a.txt"
    assert (f["location"]["start_line"], f["location"]["start_column"]) == (3, 3)
    assert f["occurrences"] == 1


def test_dirty_worktree_with_clean_index_passes(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    write(repo, "fixtures/a.txt", "clean\n")
    git(repo, "add", "fixtures/a.txt")
    write(repo, "fixtures/a.txt", f"{LITERAL}999\n")
    proc, report = _scan(repo)
    assert proc.returncode == EXIT_OK, proc.stderr
    assert (report["status"], report["findings"]) == ("ok", [])


def test_hit_counts_are_aggregated_per_pattern_and_path(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    write(repo, "fixtures/a.txt", f"{LITERAL}1 {LITERAL}2\n{LITERAL}3\n")
    git(repo, "add", "fixtures/a.txt")
    proc, report = _scan(repo)
    assert proc.returncode == EXIT_FINDINGS
    (f,) = report["findings"]
    assert f["occurrences"] == 3
    assert (f["location"]["start_line"], f["location"]["start_column"]) == (1, 1)


def test_rename_with_modification_mixed_with_add_and_modify_stays_aligned(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    old_body = "".join(f"line {i} of the original file\n" for i in range(40))
    write(repo, "fixtures/b_old.txt", old_body)
    write(repo, "fixtures/d_mod.txt", "before\n")
    commit_all(repo, "fixtures")
    # A (clean), R (similar, modified: canary on line 3), M (canary on line 2)
    write(repo, "fixtures/a_added.txt", "clean added file\n")
    git(repo, "mv", "fixtures/b_old.txt", "fixtures/c_new.txt")
    write(repo, "fixtures/c_new.txt", old_body.replace("line 2 of", f"{LITERAL}7 line 2 of"))
    write(repo, "fixtures/d_mod.txt", f"before\n{LITERAL}8\n")
    git(repo, "add", "-A", "fixtures")
    # worktree deliberately diverges from the index for the renamed file
    write(repo, "fixtures/c_new.txt", old_body)
    status = git(repo, "diff", "--cached", "--name-status", "-M").stdout.decode()
    assert any(line.startswith("R") for line in status.splitlines()), status
    proc, report = _scan(repo)
    assert proc.returncode == EXIT_FINDINGS, proc.stderr
    assert sorted(_paths(report)) == ["fixtures/c_new.txt", "fixtures/d_mod.txt"]
    by_path = {urllib.parse.unquote(f["location"]["uri"]): f for f in report["findings"]}
    assert by_path["fixtures/c_new.txt"]["location"]["start_line"] == 3
    assert by_path["fixtures/d_mod.txt"]["location"]["start_line"] == 2


def test_staged_entries_expose_the_post_image_blob_ids(tmp_path: Path) -> None:
    from decoy.ci.staged import GitBudget, read_staged_entries

    repo = _repo(tmp_path)
    body = "".join(f"row {i}\n" for i in range(30))
    write(repo, "fixtures/b_old.txt", body)
    commit_all(repo, "fixtures")
    write(repo, "fixtures/a_added.txt", "added\n")
    git(repo, "mv", "fixtures/b_old.txt", "fixtures/c_new.txt")
    write(repo, "fixtures/c_new.txt", body + "extra\n")
    write(repo, "README.md", "changed\n")
    git(repo, "add", "-A")
    entries = read_staged_entries(repo, GitBudget(seconds=10))
    by_path = {os.fsdecode(e.path): e for e in entries}
    assert sorted(by_path) == ["README.md", "fixtures/a_added.txt", "fixtures/c_new.txt"]
    assert by_path["fixtures/c_new.txt"].status == "R"
    for path, entry in by_path.items():
        expected = git(repo, "rev-parse", f":{path}").stdout.decode().strip()
        assert entry.blob_id == expected, path


def test_deleted_file_is_not_scanned(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    write(repo, "fixtures/a.txt", f"{LITERAL}1\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--no-verify", "-m", "oops")
    git(repo, "rm", "-q", "fixtures/a.txt")
    proc, report = _scan(repo)
    assert proc.returncode == EXIT_OK, proc.stderr
    assert report["status"] == "noop"


def test_files_outside_pattern_scope_are_ignored(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    write(repo, "elsewhere/a.txt", f"{LITERAL}1\n")
    manifest = ci_manifest(
        validation=False,
        patterns=[{**PATTERN, "paths": ["fixtures/**"], "exclude_paths": ["fixtures/skip/**"]}],
    )
    write(repo, MANIFEST_NAME, manifest)
    write(repo, "fixtures/skip/a.txt", f"{LITERAL}1\n")
    git(repo, "add", "elsewhere", "fixtures")
    proc, report = _scan(repo)
    assert proc.returncode == EXIT_OK, proc.stderr
    assert report["status"] == "noop"
    assert _check(report)["reason_code"] == "ci.no_staged_files"


def _check(report: dict) -> dict:
    (c,) = [c for c in report["checks"] if c["kind"] == "staged_scan"]
    return c


def test_glob_semantics(tmp_path: Path) -> None:
    pats = [
        {"id": "g.star", "literal": "STARHIT_ONE", "paths": ["fixtures/*.txt"]},
        {"id": "g.deep", "literal": "DEEPHIT_TWO", "paths": ["**/deep.cfg"]},
        {"id": "g.q", "literal": "QMARKHIT_3", "paths": ["q/f?.md"]},
    ]
    repo = _repo(tmp_path, ci_manifest(validation=False, patterns=pats))
    write(repo, "fixtures/top.txt", "STARHIT_ONE\n")
    write(repo, "fixtures/nested/top.txt", "STARHIT_ONE\n")  # `*` does not cross `/`
    write(repo, "deep.cfg", "DEEPHIT_TWO\n")  # `**/` matches zero directories
    write(repo, "a/b/c/deep.cfg", "DEEPHIT_TWO\n")
    write(repo, "q/f1.md", "QMARKHIT_3\n")
    write(repo, "q/f12.md", "QMARKHIT_3\n")  # `?` is exactly one character
    git(repo, "add", "-A", "fixtures", "deep.cfg", "a", "q")
    proc, report = _scan(repo)
    assert proc.returncode == EXIT_FINDINGS
    assert sorted(_paths(report)) == ["a/b/c/deep.cfg", "deep.cfg", "fixtures/top.txt", "q/f1.md"]


def test_symlink_in_scope_is_refused_not_followed(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    write(repo, "elsewhere.txt", f"{LITERAL}1\n")
    (repo / "fixtures").mkdir()
    os.symlink("../elsewhere.txt", repo / "fixtures" / "link.txt")
    git(repo, "add", "fixtures/link.txt")
    proc, report = _scan(repo)
    assert proc.returncode == EXIT_USAGE, proc.stderr
    assert report["status"] == "partial"
    assert _check(report)["reason_code"] == "ci.staged_unsupported_entry"


def test_submodule_in_scope_is_refused(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    sub = make_repo(tmp_path / "sub")
    write(sub, "f.txt", "x\n")
    commit_all(sub)
    sha = git(sub, "rev-parse", "HEAD").stdout.decode().strip()
    git(repo, "update-index", "--add", "--cacheinfo", f"160000,{sha},fixtures/vendored")
    proc, report = _scan(repo)
    assert proc.returncode == EXIT_USAGE, proc.stderr
    assert report["status"] == "partial"
    assert _check(report)["reason_code"] == "ci.staged_unsupported_entry"


def test_unmerged_index_is_refused(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    write(repo, "fixtures/c.txt", "base\n")
    commit_all(repo, "c")
    git(repo, "checkout", "-q", "-b", "other")
    write(repo, "fixtures/c.txt", "other\n")
    commit_all(repo, "other")
    git(repo, "checkout", "-q", "main")
    write(repo, "fixtures/c.txt", "main\n")
    commit_all(repo, "main")
    merge = git(repo, "merge", "other", check=False)
    assert merge.returncode != 0
    proc, report = _scan(repo)
    assert proc.returncode == EXIT_USAGE, proc.stderr
    assert report["status"] == "partial"
    assert _check(report)["reason_code"] == "ci.staged_unmerged"


def test_binary_and_non_utf8_blobs_yield_file_level_findings(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    write(repo, "fixtures/bin.dat", b"\x00\x01" + LITERAL.encode() + b"\x00")
    write(repo, "fixtures/latin1.txt", b"caf\xe9 " + LITERAL.encode() + b"\n")
    git(repo, "add", "-f", "fixtures")
    proc, report = _scan(repo)
    assert proc.returncode == EXIT_FINDINGS, proc.stderr
    assert sorted(_paths(report)) == ["fixtures/bin.dat", "fixtures/latin1.txt"]
    for f in report["findings"]:
        assert f["location"]["start_line"] is None


def test_unusual_filenames_survive_nul_separated_parsing_and_uri_encoding(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    names = [
        "fixtures/with space.txt",
        "fixtures/café 中.txt",
        "fixtures/-rf",
        "fixtures/--cached",
        "fixtures/HEAD~1",
        "fixtures/:(top)x",
        "fixtures/tab\there.txt",
        "fixtures/new\nline.txt",
        'fixtures/quote"d.txt',
    ]
    for n in names:
        write(repo, n, f"{LITERAL}1\n")
    git(repo, "add", "-A", "fixtures")
    proc, report = _scan(repo)
    assert proc.returncode == EXIT_FINDINGS, proc.stderr
    assert sorted(_paths(report)) == sorted(names)
    for f in report["findings"]:
        assert "\n" not in f["location"]["uri"] and " " not in f["location"]["uri"]


def test_per_file_and_total_byte_caps_are_partial_not_clean(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    write(repo, "fixtures/big.txt", b"a" * (1024 * 1024 + 1))
    git(repo, "add", "fixtures")
    proc, report = _scan(repo)
    assert proc.returncode == EXIT_USAGE, proc.stderr
    assert (report["status"], _check(report)["reason_code"]) == ("partial", "ci.staged_scan_limit")
    git(repo, "reset", "-q")
    (repo / "fixtures" / "big.txt").unlink()
    for i in range(6):
        write(repo, f"fixtures/m{i}.txt", b"b" * 1_000_000)
    git(repo, "add", "fixtures")
    proc, report = _scan(repo)
    assert proc.returncode == EXIT_USAGE, proc.stderr
    assert _check(report)["reason_code"] == "ci.staged_scan_limit"


def test_hits_in_the_scanned_subset_are_still_reported_when_a_limit_trips(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    write(repo, "fixtures/a_hit.txt", f"{LITERAL}1\n")
    write(repo, "fixtures/z_big.txt", b"a" * (1024 * 1024 + 1))
    git(repo, "add", "fixtures")
    proc, report = _scan(repo)
    assert proc.returncode == EXIT_USAGE  # incompleteness outranks the findings exit
    assert report["status"] == "partial"
    assert _paths(report) == ["fixtures/a_hit.txt"]


def test_manifest_may_lower_the_file_cap(tmp_path: Path) -> None:
    manifest = (
        ci_manifest(
            validation=False,
            patterns=[PATTERN],
        )
        + "  limits:\n    max_files: 2\n"
    )
    repo = _repo(tmp_path, manifest)
    for i in range(3):
        write(repo, f"fixtures/f{i}.txt", "clean\n")
    git(repo, "add", "fixtures")
    proc, report = _scan(repo)
    assert proc.returncode == EXIT_USAGE, proc.stderr
    assert _check(report)["reason_code"] == "ci.staged_scan_limit"


def test_finding_group_cap(tmp_path: Path) -> None:
    manifest = (
        ci_manifest(validation=False, patterns=[PATTERN]) + "  limits:\n    max_finding_groups: 3\n"
    )
    repo = _repo(tmp_path, manifest)
    for i in range(5):
        write(repo, f"fixtures/f{i}.txt", f"{LITERAL}1\n")
    git(repo, "add", "fixtures")
    proc, report = _scan(repo)
    assert proc.returncode == EXIT_USAGE, proc.stderr
    assert report["status"] == "partial"
    assert len(report["findings"]) == 3
    assert _check(report)["reason_code"] == "ci.staged_scan_limit"


def test_git_timeout_is_a_runtime_failure_not_a_clean_scan(tmp_path: Path) -> None:
    manifest = (
        ci_manifest(validation=False, patterns=[PATTERN]) + "  limits:\n    max_git_seconds: 1\n"
    )
    repo = _repo(tmp_path, manifest)
    write(repo, "fixtures/a.txt", "clean\n")
    git(repo, "add", "fixtures")
    # A git that hangs on the staged diff (a stand-in for a stalled filesystem). `exec`
    # makes the sleep BE the process, so the budget's kill is what ends it, not the sleep.
    shim_dir = tmp_path / "shim"
    shim_dir.mkdir()
    shim = shim_dir / "git"
    shim.write_text(
        '#!/bin/sh\ncase "$*" in *"diff --cached"*) exec sleep 30;; esac\n'
        f'exec {shutil.which("git")} "$@"\n',
        encoding="utf-8",
    )
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC)
    env = {"PATH": f"{shim_dir}{os.pathsep}{os.environ['PATH']}"}
    started = time.monotonic()
    proc, report = _scan(repo, env=env)
    assert time.monotonic() - started < 15, "the 1s Git budget must actually stop the process"
    assert proc.returncode == EXIT_RUNTIME, proc.stderr
    assert (report["status"], report["exit_code"]) == ("partial", EXIT_RUNTIME)
    assert _check(report)["reason_code"] == "ci.git_failure"
    assert report["findings"] == []


def test_no_staged_files_is_a_noop(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    proc, report = _scan(repo)
    assert proc.returncode == EXIT_OK, proc.stderr
    assert (report["status"], _check(report)["reason_code"]) == ("noop", "ci.no_staged_files")


def test_scan_executes_no_repository_configured_program(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    marker = tmp_path / "executed.marker"
    script = tmp_path / "touch.sh"
    script.write_text(f"#!/bin/sh\necho ran >> {marker}\ncat\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    git(repo, "config", "diff.external", str(script))
    git(repo, "config", "diff.evil.textconv", str(script))
    git(repo, "config", "diff.evil.command", str(script))
    git(repo, "config", "core.fsmonitor", str(script))
    git(repo, "config", "filter.evil.clean", str(script))
    git(repo, "config", "filter.evil.smudge", str(script))
    git(repo, "config", "core.pager", str(script))
    write(repo, ".gitattributes", "fixtures/** diff=evil filter=evil\n")
    write(repo, "fixtures/a.txt", f"{LITERAL}1\n")
    git(repo, "add", "-f", ".gitattributes")
    git(repo, "add", "-f", "fixtures/a.txt")
    marker.unlink(
        missing_ok=True
    )  # `git add` itself ran the clean filter; only the scan is under test
    proc, _report = _scan(repo)
    assert proc.returncode == EXIT_FINDINGS, proc.stderr
    assert not marker.exists(), marker.read_text()


def test_scan_from_a_subdirectory_reports_repo_relative_uris(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    write(repo, "fixtures/a.txt", f"{LITERAL}1\n")
    git(repo, "add", "fixtures")
    (repo / "sub").mkdir()
    proc = ci_check(repo / "sub", "--format", "json", manifest="../" + MANIFEST_NAME)
    report = parse_stdout(proc)
    assert proc.returncode == EXIT_FINDINGS, proc.stderr
    assert _paths(report) == ["fixtures/a.txt"]


@pytest.mark.parametrize("status_sample", ["C"])
def test_copy_entries_use_the_two_field_form_too(tmp_path: Path, status_sample: str) -> None:
    """`-C` style entries are `C75\\0src\\0dst\\0`; the parser must not desync on them."""
    from decoy.ci.staged import parse_name_status_z

    raw = b"A\0a.txt\0C75\0src.txt\0dst.txt\0M\0m.txt\0R100\0old\0new\0D\0gone\0"
    assert [(s, os.fsdecode(p)) for s, p in parse_name_status_z(raw)] == [
        ("A", "a.txt"),
        ("C", "dst.txt"),
        ("M", "m.txt"),
        ("R", "new"),
        ("D", "gone"),
    ]
    with pytest.raises(ValueError):
        parse_name_status_z(b"A\0a.txt\0R100\0only-one-field\0")


def test_exact_boundary_sizes_are_accepted(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    write(repo, "fixtures/exact.txt", b"a" * (1024 * 1024))  # == max_blob_bytes
    git(repo, "add", "fixtures")
    proc, report = _scan(repo)
    assert proc.returncode == EXIT_OK, proc.stderr
    assert (report["status"], report["findings"]) == ("ok", [])
    # five 1 MiB files total exactly 5 MiB == max_total_bytes
    git(repo, "reset", "-q")
    (repo / "fixtures" / "exact.txt").unlink()
    for i in range(5):
        write(repo, f"fixtures/m{i}.txt", bytes([97 + i]) * (1024 * 1024))
    git(repo, "add", "fixtures")
    proc, report = _scan(repo)
    assert proc.returncode == EXIT_OK, proc.stderr
    assert report["status"] == "ok"


def test_file_count_boundary_is_inclusive(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    for i in range(200):
        write(repo, f"fixtures/f{i:03d}.txt", f"clean {i}\n")
    git(repo, "add", "fixtures")
    proc, report = _scan(repo)
    assert proc.returncode == EXIT_OK, proc.stderr
    assert report["status"] == "ok"


def test_replace_refs_cannot_swap_the_bytes_that_get_scanned(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    write(repo, "fixtures/a.txt", f"{LITERAL}1\n")
    git(repo, "add", "fixtures/a.txt")
    dirty = git(repo, "rev-parse", ":fixtures/a.txt").stdout.decode().strip()
    clean = (
        git(repo, "hash-object", "-w", "--stdin", input=b"nothing to see\n").stdout.decode().strip()
    )
    git(repo, "replace", "-f", dirty, clean)
    # control: with replace refs honored, git itself would hand back the clean bytes
    assert git(repo, "cat-file", "-p", dirty).stdout == b"nothing to see\n"
    proc, report = _scan(repo)
    assert proc.returncode == EXIT_FINDINGS, proc.stderr
    assert _paths(report) == ["fixtures/a.txt"]


def test_the_execution_controls_have_teeth(tmp_path: Path) -> None:
    """Negative control for the no-program test: a plain `git diff --cached` DOES run them."""
    repo = _repo(tmp_path)
    marker = tmp_path / "plain-git.marker"
    script = tmp_path / "touch.sh"
    script.write_text(f"#!/bin/sh\necho ran >> {marker}\ncat\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    git(repo, "config", "diff.external", str(script))
    write(repo, "fixtures/a.txt", f"{LITERAL}1\n")
    git(repo, "add", "fixtures/a.txt")
    git(repo, "commit", "-q", "-m", "x")
    write(repo, "fixtures/a.txt", f"{LITERAL}2\n")
    git(repo, "add", "fixtures/a.txt")
    git(repo, "diff", "--cached")
    assert marker.exists(), "the repo-configured program must run for a plain git diff"


def test_type_changes_are_scanned_or_refused_never_skipped(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    write(repo, "elsewhere.txt", "target\n")
    write(repo, "fixtures/regular.txt", "clean\n")
    (repo / "fixtures").mkdir(exist_ok=True)
    os.symlink("../elsewhere.txt", repo / "fixtures" / "was_link.txt")
    commit_all(repo, "types")
    # regular -> symlink: refused (never followed)
    (repo / "fixtures" / "regular.txt").unlink()
    os.symlink("../elsewhere.txt", repo / "fixtures" / "regular.txt")
    git(repo, "add", "fixtures/regular.txt")
    proc, report = _scan(repo)
    assert proc.returncode == EXIT_USAGE, proc.stderr
    assert _check(report)["reason_code"] == "ci.staged_unsupported_entry"
    git(repo, "reset", "-q", "--hard")
    # symlink -> regular file holding the literal: the new regular post-image IS scanned
    (repo / "fixtures" / "was_link.txt").unlink()
    write(repo, "fixtures/was_link.txt", f"{LITERAL}1\n")
    git(repo, "add", "fixtures/was_link.txt")
    assert git(repo, "diff", "--cached", "--name-status").stdout.decode().startswith("T")
    proc, report = _scan(repo)
    assert proc.returncode == EXIT_FINDINGS, proc.stderr
    assert _paths(report) == ["fixtures/was_link.txt"]


def test_a_hit_in_a_path_that_cannot_be_reported_still_blocks(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    write(repo, "fixtures/back\\slash.txt", f"{LITERAL}1\n")  # a backslash is legal in a Git path
    git(repo, "add", "fixtures")
    proc, report = _scan(repo)
    assert proc.returncode == EXIT_USAGE, proc.stderr
    assert report["status"] == "partial"
    assert _check(report)["reason_code"] == "ci.staged_unsupported_entry"
    assert report["findings"] == []
