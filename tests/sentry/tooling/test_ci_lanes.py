"""CI lane sentry (CI-L1b): every CLI workflow job, marker and test folder has an automatic lane.

The real tree is the negative control; each seeded case edits a deep copy of it and asserts its own
finding. The rules and their differences from the engine copy are in
tests/sentry/tooling/_ci_lanes.py. Acceptance items 12 to 15 of the CI-L1 handoff are marked.
"""

from __future__ import annotations

import copy
from dataclasses import replace
from typing import Any

import pytest
from tests.sentry.tooling import _ci_lanes as lanes

TREE = lanes.load()


def seeded() -> lanes.Tree:
    return copy.deepcopy(TREE)


def job(tree: lanes.Tree, wf: str, key: str) -> dict[str, Any]:
    return tree.workflows[wf]["jobs"][key]


def with_on(doc: dict[Any, Any], on: Any) -> dict[Any, Any]:
    """The workflow with its triggers replaced. YAML 1.1 parses the `on:` key as True."""
    out = {k: v for k, v in doc.items() if k not in (True, "on")}
    out[True] = on
    return out


def has(found: list[str], text: str) -> bool:
    return any(text in f for f in found)


def test_real_tree_has_no_findings() -> None:
    assert lanes.findings(TREE) == []


# --- item 12: the merge tier matches the workflows in both directions ----------------------


def test_required_jobs_match_workflows() -> None:
    t = seeded()
    ci = t.workflows["ci.yml"]["jobs"]
    ci["ruff-renamed"] = ci.pop("ruff")
    found = lanes.registry_findings(t)
    assert has(found, "R2 ci.yml:ruff: merge job does not exist")
    assert has(found, "R3 ci.yml:ruff-renamed")
    t = seeded()
    t.workflows["ci.yml"]["jobs"]["extra"] = {"runs-on": "ubuntu-latest", "timeout-minutes": 1}
    assert has(lanes.registry_findings(t), "R3 ci.yml:extra")
    t = seeded()
    t.required["merge"][0]["jobs"].remove("pytest")
    assert has(lanes.registry_findings(t), "R3 ci.yml:pytest")


def test_matrix_must_be_the_supported_pythons() -> None:
    t = seeded()
    job(t, "ci.yml", "pytest")["strategy"]["matrix"]["python"].append("3.13")
    assert has(lanes.registry_findings(t), "R2 ci.yml:pytest: merge job has a templated name")
    t = seeded()
    job(t, "ci.yml", "pytest")["name"] = "pytest ${{ matrix.os }}"
    assert has(lanes.registry_findings(t), "R2 ci.yml:pytest")
    t = seeded()
    job(t, "ci.yml", "ruff")["name"] = "ruff ${{ github.ref }}"
    assert has(lanes.registry_findings(t), "R2 ci.yml:ruff")


def test_merge_job_rules() -> None:
    t = seeded()
    job(t, "ci.yml", "ruff")["if"] = "always()"
    assert has(lanes.registry_findings(t), "R2 ci.yml:ruff: merge job has an `if`")
    t = seeded()
    job(t, "ci.yml", "ruff")["runs-on"] = ["self-hosted", "x"]
    assert has(lanes.registry_findings(t), "is self-hosted")
    t = seeded()
    t.required["merge"].append({"workflow": "release-smoke.yml", "jobs": ["fresh-install"]})
    assert has(lanes.registry_findings(t), "R2 release-smoke.yml: merge workflow has no pull")


def test_registry_schema_is_closed() -> None:
    cases: list[tuple[str, lanes.Tree]] = []
    t = seeded()
    t.unlaned["path_filter"][0]["extra"] = 1
    cases.append(("keys", t))
    t = seeded()
    t.unlaned["path_filter"][0]["reason"] = " "
    cases.append(("non-empty", t))
    t = seeded()
    t.unlaned["path_filter"].append(dict(t.unlaned["path_filter"][0]))
    cases.append(("duplicate", t))
    t = seeded()
    t.required["bogus"] = []
    cases.append(("unknown table", t))
    for text, tree in cases:
        assert has(lanes.registry_findings(tree), "R1"), text
        assert has(lanes.registry_findings(tree), text), text


# --- item 13: markers and workflow triggers ------------------------------------------------


def test_new_deselected_marker_needs_a_lane_or_an_unlaned_entry() -> None:
    t = seeded()
    ini = t.pyproject["tool"]["pytest"]["ini_options"]
    ini["markers"] = ["slowx: x"]
    ini["addopts"] = '-m "not slowx"'
    assert has(lanes.marker_findings(t), "M2 marker 'slowx'")
    t.unlaned["marker"] = [{"name": "slowx", "reason": "test"}]
    assert lanes.marker_findings(t) == []


def test_unreadable_expression_is_no_lane() -> None:
    t = seeded()
    job(t, "ci.yml", "pytest")["steps"] = [{"run": 'pytest tests -m "a + b"'}]
    assert has(lanes.marker_findings(t), "M4 ci.yml:pytest")


@pytest.mark.parametrize(
    "run",
    [
        "pytest -m x tests/unit",
        "python -m pytest -mx tests/unit",
        "uv run --frozen pytest -m y -m x tests/unit",
        'bash -c "pytest -m x tests/unit"',
        "FOO=1 pytest tests/unit \\\n  -m x --tb=short",
    ],
)
def test_spellings_are_read_as_the_lane(run: str) -> None:
    t = seeded()
    job(t, "ci.yml", "pytest")["steps"] = [{"run": run}]
    (lane,) = [ln for ln in lanes.lanes(t) if ln.job == "pytest"]
    assert lane.expr == "x" and lane.paths == ("tests/unit",) and not lane.bad


def test_workflow_without_automatic_trigger_needs_an_unlaned_entry() -> None:
    t = seeded()
    t.workflows["release-smoke.yml"] = with_on(
        t.workflows["release-smoke.yml"], {"workflow_dispatch": None}
    )
    assert has(lanes.trigger_findings(t), "T1 release-smoke.yml: no automatic trigger")
    t.unlaned["workflow"] = [{"file": "release-smoke.yml", "reason": "x"}]
    assert not has(lanes.trigger_findings(t), "T1")
    t.unlaned["workflow"].append({"file": "ci.yml", "reason": "x"})
    assert has(lanes.trigger_findings(t), "T1 ci.yml: has an automatic trigger")


def test_path_filter_needs_its_named_exception() -> None:
    t = seeded()
    t.unlaned["path_filter"] = []
    assert has(lanes.trigger_findings(t), "T2 regen-diagrams.yml: path filter on push")
    t = seeded()
    t.workflows["ci.yml"] = with_on(t.workflows["ci.yml"], {"pull_request": {"paths": ["src/**"]}})
    assert has(lanes.trigger_findings(t), "T2 ci.yml")
    t = seeded()
    t.unlaned["path_filter"].append({"file": "gone.yml", "reason": "x"})
    assert has(lanes.trigger_findings(t), "'gone.yml' does not exist")


def test_timeout_and_concurrency_rules() -> None:
    t = seeded()
    del job(t, "ci.yml", "ruff")["timeout-minutes"]
    assert has(lanes.trigger_findings(t), "T3 ci.yml:ruff")
    t = seeded()
    del t.workflows["ci.yml"]["concurrency"]
    assert has(lanes.trigger_findings(t), "T4 ci.yml: pull_request workflow lacks")


# --- item 14: test paths and the daily cron ------------------------------------------------


def test_lanes_collect_every_test_folder() -> None:
    assert TREE.test_dirs == ["tests/e2e", "tests/sentry", "tests/unit"]
    t = seeded()
    steps = job(t, "ci.yml", "pytest")["steps"]
    job(t, "ci.yml", "pytest")["steps"] = [s for s in steps if "tests/e2e" not in s.get("run", "")]
    assert has(lanes.path_findings(t), "P1 tests/e2e: no automatic pytest lane")


def test_ignored_file_must_run_in_another_job() -> None:
    t = seeded()
    t = replace(t, scripts={k: v.replace("test_import_layers", "x") for k, v in t.scripts.items()})
    assert has(lanes.path_findings(t), "--ignore tests/sentry/layout/test_import_layers.py")
    t = seeded()
    del t.workflows["ci.yml"]["jobs"]["layers-gate"]
    assert has(lanes.path_findings(t), "runs in no other job")


def test_ci_cron_is_daily() -> None:
    crons = [e["cron"] for e in lanes._on(TREE.workflows["ci.yml"])["schedule"]]
    assert crons and all(c.split()[2:] == ["*", "*", "*"] for c in crons), crons


# --- item 15: the drift canary is the one reported, unrequired scheduled lane -------------


def test_drift_canary_is_reported_once_and_not_required() -> None:
    assert lanes.reported(TREE) == [("release-smoke.yml", "fresh-install")]
    t = seeded()
    t.required["merge"].append({"workflow": "release-smoke.yml", "jobs": ["fresh-install"]})
    assert has(lanes.canary_findings(t), "not one reported, unrequired lane")
    t = seeded()
    (site,) = [s for s in t.policy["engine_site"] if s["kind"] == "drift-canary"]
    site["reason"] = ""
    assert has(lanes.canary_findings(t), "drift canary has no reason")
