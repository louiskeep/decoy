"""A10: build-blocking leak sentry for every F43 output surface.

One parameterized sentry guards the CLASS: distinctive canaries are seeded into a
staged blob, a pattern literal, a pipeline scalar, an engine exception source, an
evidence manifest, a manifest field, and the absolute temp root. The CLI is then run
(real process) over clean / finding / refused / partial paths in JSON, SARIF and
Markdown, on stdout, stderr, a written file, and in verbose mode. Neither a full
canary nor an identifying substring of one may appear in ANY emitted byte.

A future emitter inherits the guard by adding its flag value to FORMATS.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

import pytest
from tests.ci_support import (
    CLEAN_PIPELINE,
    MANIFEST_NAME,
    assert_valid_sarif,
    ci_check,
    commit_all,
    git,
    make_evidence,
    make_repo,
    parse_stdout,
    run_decoy,
    write,
    write_clean_pipeline,
)

from decoy.cli.exit_codes import EXIT_OK, EXIT_RUNTIME, EXIT_USAGE

REPO_ROOT = Path(__file__).resolve().parents[2]

CANARIES = {
    "blob": "BLOBVALUE_4d1b7a2e",
    "literal": "LITERALSECRET_91c2e5f0",
    "pipeline_scalar": "PIPESCALAR_b7e30d19",
    "exception": "ENGINEEXC_5a8f26c3",
    "evidence": "EVIDENCEVAL_c40e9a71",
    "manifest": "MANIFESTVAL_2f6d8b04",
}
ROOT_MARK = "leakroot_5b2e9d"


def _needles(tmp_path: Path) -> list[str]:
    needles: list[str] = []
    for full in CANARIES.values():
        name, tail = full.split("_")
        needles += [full, name, tail]
    needles += [ROOT_MARK, str(tmp_path)]
    return needles


FORMATS = ("json", "sarif", "markdown")
SCENARIOS = ("clean", "finding", "refused", "partial")

# (report status, exit integer). The sentry must never pass because the command
# produced nothing: each cell asserts the REAL outcome before it scans bytes.
EXPECTED = {
    "clean": ("ok", EXIT_OK),
    "finding": ("findings", EXIT_USAGE),
    "refused": ("refused", EXIT_USAGE),
    "partial": ("partial", EXIT_RUNTIME),
}


@dataclass
class Case:
    repo: Path


def _manifest(pattern_literal: str, *, evidence: bool, extra: str = "") -> str:
    ev = (
        "  evidence:\n    - id: protected-output\n      manifest: build/evidence.json\n"
        if evidence
        else ""
    )
    return (
        "schema_version: decoy-ci/v1\n"
        "pipelines:\n  - id: primary\n    path: pipeline.yaml\n"
        "checks:\n  validation:\n    enabled: true\n    mode: full\n    pipelines: [primary]\n    fail_on_warning: false\n"
        f"{ev}\n"
        "staged_scan:\n  enabled: true\n  patterns:\n"
        f"    - id: pii.seeded-test-identifier\n      literal: {json.dumps(pattern_literal)}\n"
        '      paths: ["fixtures/**"]\n      exclude_paths: []\n'
        f"{extra}"
    )


def _pipeline(provider: str = "person_email") -> str:
    # the pipeline SCALAR canary rides in a real, existing source path
    return CLEAN_PIPELINE.replace("data/in.csv", f"data/{CANARIES['pipeline_scalar']}.csv").replace(
        "person_email", provider
    )


def build(tmp_path: Path, scenario: str) -> Case:
    repo = make_repo(tmp_path / ROOT_MARK)
    write_clean_pipeline(repo, text=_pipeline())
    write(repo, f"data/{CANARIES['pipeline_scalar']}.csv", "email\na@example.invalid\n")
    literal = CANARIES["literal"]
    blob_line = f"row,{CANARIES['blob']}\n"
    if scenario == "clean":
        make_evidence(repo)
        write(repo, MANIFEST_NAME, _manifest(literal, evidence=True))
        commit_all(repo)
        write(repo, "fixtures/a.txt", blob_line)  # contains the blob canary, not the literal
        git(repo, "add", "fixtures/a.txt")
        return Case(repo)
    if scenario == "finding":
        make_evidence(repo)
        ev = json.loads((repo / "build" / "evidence.json").read_text())
        ev["output_fingerprints"]["customers"]["path"] = f"out/{CANARIES['evidence']}.csv"
        ev["notes"] = CANARIES["evidence"]
        (repo / "build" / "evidence.json").write_text(json.dumps(ev), encoding="utf-8")
        write(repo, "pipeline.yaml", _pipeline(provider=CANARIES["exception"]))
        write(repo, MANIFEST_NAME, _manifest(literal, evidence=True))
        commit_all(repo)
        write(repo, "fixtures/a.txt", f"row,{literal},{CANARIES['blob']}\n")
        git(repo, "add", "fixtures/a.txt")
        return Case(repo)
    if scenario == "refused":
        write(
            repo,
            MANIFEST_NAME,
            _manifest(literal, evidence=False, extra=f"surprise: {CANARIES['manifest']}\n"),
        )
        commit_all(repo)
        return Case(repo)
    if scenario == "partial":
        write(repo, MANIFEST_NAME, _manifest(literal, evidence=False))
        commit_all(repo)
        write(repo, "fixtures/a.txt", f"row,{literal},{CANARIES['blob']}\n")
        git(repo, "add", "fixtures/a.txt")
        (repo / ".git" / "index").write_bytes(b"corrupt index with " + CANARIES["blob"].encode())
        return Case(repo)
    raise AssertionError(scenario)


def _assert_real_report(fmt: str, text: str, scenario: str, status: str) -> None:
    if fmt == "json":
        doc = json.loads(text)
        assert doc["schema_version"] == "decoy-ci-report/v1" and doc["status"] == status
        if scenario == "finding":
            assert doc["findings"], "the finding scenario must really produce findings"
    elif fmt == "sarif":
        doc = json.loads(text)
        assert_valid_sarif(doc)
        if scenario == "finding":
            assert doc["runs"][0]["results"], "the finding scenario must really produce results"
    else:
        assert text.startswith("# Decoy CI") and status in text


def _snapshot(repo: Path) -> dict[str, str]:
    """Content digest of every regular file outside .git: catches created AND modified files."""
    return {
        p.relative_to(repo).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in repo.rglob("*")
        if ".git" not in p.parts and p.is_file() and not p.is_symlink()
    }


def _walk_keys(node, found: set[str]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            found.add(k)
            _walk_keys(v, found)
    elif isinstance(node, list):
        for v in node:
            _walk_keys(v, found)


@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize("scenario", SCENARIOS)
@pytest.mark.parametrize("surface", ["stdout", "file", "verbose-stdout", "verbose-file"])
def test_no_canary_or_identifying_substring_reaches_any_byte(
    tmp_path: Path, scenario: str, fmt: str, surface: str
) -> None:
    case = build(tmp_path, scenario)
    args = ["--format", fmt]
    if surface.startswith("verbose"):
        args.append("--verbose")
    if surface.endswith("file"):
        args += ["--output", f"report.{fmt}"]
    before = _snapshot(case.repo)
    proc = ci_check(case.repo, *args)
    status, code = EXPECTED[scenario]
    assert proc.returncode == code, (proc.returncode, proc.stderr[-400:])

    artifacts = {"stdout": proc.stdout, "stderr": proc.stderr}
    out_file = case.repo / f"report.{fmt}"
    if surface.endswith("file"):
        assert out_file.exists() and proc.stdout == ""
        artifacts["file"] = out_file.read_text(encoding="utf-8")
    report_text = artifacts.get("file") or proc.stdout
    assert report_text.strip(), "the report surface must not be empty"
    _assert_real_report(fmt, report_text, scenario, status)
    after = _snapshot(case.repo)
    # no stray artifact: only the requested report file may appear or change (A9c). The engine's
    # cwd-relative `logs/decoy_engine.log` is NOT exempt: `decoy ci` must not write it, and every
    # created or modified file is scanned for the canaries below.
    changed = {rel for rel, digest in after.items() if before.get(rel) != digest}
    assert changed <= {out_file.name}, changed
    for rel in changed:
        artifacts[f"file:{rel}"] = (case.repo / rel).read_bytes().decode("utf-8", "replace")

    for where, text in artifacts.items():
        for needle in _needles(tmp_path):
            assert needle not in text, (
                f"{needle!r} leaked into {where} ({scenario}/{fmt}/{surface})"
            )

    if fmt == "sarif":
        doc = json.loads(report_text)
        keys: set[str] = set()
        _walk_keys(doc, keys)
        assert not keys & {
            "snippet",
            "contextRegion",
            "invocations",
            "attachments",
            "stacks",
            "exception",
        }


def test_exception_prose_is_never_echoed(tmp_path: Path) -> None:
    """`str(exc)` of the real engine/git failures carries the canaries and the temp root."""
    for scenario in ("finding", "partial"):
        case = build(tmp_path / scenario, scenario)
        direct = run_decoy(["validate", "pipeline.yaml", "--json"], case.repo)
        if scenario == "finding":
            assert CANARIES["exception"] in direct.stdout  # the unsafe prose really exists upstream
        proc = ci_check(case.repo, "--format", "json", "--verbose")
        assert parse_stdout(proc)["status"] == EXPECTED[scenario][0]
        assert CANARIES["exception"] not in proc.stdout + proc.stderr
        assert ROOT_MARK not in proc.stdout + proc.stderr


# ---- the sanctioned raw sink: --unsafe-debug-log ------------------------------------


def test_debug_log_flag_is_hidden_from_help_and_the_cli_reference() -> None:
    help_text = run_decoy(["ci", "check", "--help"], REPO_ROOT).stdout
    assert "--format" in help_text and "--output" in help_text
    assert "unsafe" not in help_text and "debug-log" not in help_text
    assert "unsafe-debug-log" not in (REPO_ROOT / "docs" / "cli-reference.md").read_text(
        encoding="utf-8"
    )


def test_debug_log_flag_is_never_passed_by_any_shipped_artifact() -> None:
    shipped = [
        REPO_ROOT / ".pre-commit-hooks.yaml",
        *sorted((REPO_ROOT / "integrations").rglob("*.yml")),
    ]
    assert len(shipped) >= 3
    for path in shipped:
        assert "unsafe-debug-log" not in path.read_text(encoding="utf-8"), path


def test_debug_log_is_only_created_when_explicitly_given_and_never_reaches_streams(
    tmp_path: Path,
) -> None:
    case = build(tmp_path, "partial")
    plain = ci_check(case.repo, "--format", "json")
    assert plain.returncode == EXPECTED["partial"][1], plain.stderr
    assert not list(case.repo.glob("*debug*")) and not list(case.repo.glob("*.log"))
    with_flag = ci_check(case.repo, "--format", "json", "--unsafe-debug-log", "unsafe-debug.txt")
    log = case.repo / "unsafe-debug.txt"
    assert log.exists() and log.read_text(encoding="utf-8").strip()
    assert with_flag.stdout == plain.stdout  # the safe report is byte-identical with the hatch on
    for stream in (with_flag.stdout, with_flag.stderr):
        for needle in _needles(tmp_path):
            assert needle not in stream
        for line in log.read_text(encoding="utf-8").splitlines():
            if len(line.strip()) >= 12:
                assert line.strip() not in stream
    assert re.search(r"unsafe", with_flag.stderr, re.IGNORECASE)  # a fixed warning line, no content


def test_debug_log_refuses_stdout_and_the_report_path(tmp_path: Path) -> None:
    case = build(tmp_path, "clean")
    assert (
        ci_check(case.repo, "--format", "json").returncode == EXIT_OK
    )  # the control: it works without the hatch
    dash = ci_check(case.repo, "--format", "json", "--unsafe-debug-log", "-")
    assert dash.returncode == EXIT_USAGE and dash.stdout == ""
    same = ci_check(
        case.repo, "--format", "json", "--output", "r.json", "--unsafe-debug-log", "r.json"
    )
    assert same.returncode == EXIT_USAGE and not (case.repo / "r.json").exists()
