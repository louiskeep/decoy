"""The D7 baseline may only shrink: the real ratchet rejects every gained error site.

Each case builds a scratch git repo whose base commit holds the committed D7 baseline, edits the
working tree, and runs ``scripts/dev/ratchet_check.py`` against the base. A new site added to the
head baseline is still a gained key, so editing the baseline cannot launder a new error site.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from tests.sentry.cli_text import _error_sites as sites

ROOT = sites.ROOT
SCRIPT = ROOT / "scripts" / "dev" / "ratchet_check.py"
BASELINE_REL = "tests/sentry/baselines/one-error-emitter.json"
REGISTRY_REL = "scripts/dev/sentry_registry.toml"
REGISTRY = f'[[sentry]]\nid = "one-error-emitter"\nbaseline = "{BASELINE_REL}"\n'


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
    )


def _write_baseline(repo: Path, doc: dict) -> None:
    (repo / BASELINE_REL).write_text(json.dumps(doc), encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "tests/sentry/baselines").mkdir(parents=True)
    (tmp_path / "scripts/dev").mkdir(parents=True)
    (tmp_path / REGISTRY_REL).write_text(REGISTRY, encoding="utf-8")
    (tmp_path / BASELINE_REL).write_text((ROOT / BASELINE_REL).read_text(encoding="utf-8"))
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


def _check(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(repo), "--base", "HEAD"],
        capture_output=True,
        text=True,
    )


def _head(repo: Path) -> dict:
    return json.loads((repo / BASELINE_REL).read_text(encoding="utf-8"))


def _gain(repo: Path, key: str) -> None:
    doc = _head(repo)
    reason = next(iter(doc["entries"].values()))["reason"]
    doc["entries"][key] = {"reason": reason}
    _write_baseline(repo, doc)


def test_the_unchanged_baseline_passes(repo: Path) -> None:
    res = _check(repo)
    assert res.returncode == 0, res.stdout + res.stderr


def test_deleting_a_converted_entry_passes(repo: Path) -> None:
    doc = _head(repo)
    doc["entries"].pop(sorted(doc["entries"])[0])
    _write_baseline(repo, doc)
    res = _check(repo)
    assert res.returncode == 0, res.stdout + res.stderr


def test_a_new_site_added_to_the_head_baseline_is_rejected(repo: Path) -> None:
    (key,) = sites.sites_in_source(
        "def g(s):\n    s.err_console.print(error('error:'), 'new')\n", "cli/new.py"
    )
    _gain(repo, key)
    res = _check(repo)
    assert res.returncode == 1
    assert key in res.stdout + res.stderr


def test_a_changed_retained_expression_is_rejected(repo: Path) -> None:
    doc = _head(repo)
    old = next(k for k in sorted(doc["entries"]) if k.startswith("cli/cockpit.py"))
    scope = old.split("::")[1]
    (edited,) = sites.sites_in_source(
        f"def {scope.split('.')[-1]}(s):\n    s.err_console.print(error('error:'), 'edited')\n",
        "cli/cockpit.py",
    )
    doc["entries"].pop(old)
    _write_baseline(repo, doc)
    _gain(repo, edited)
    res = _check(repo)
    assert res.returncode == 1
    assert edited in res.stdout + res.stderr


@pytest.mark.parametrize(
    "src",
    [
        "def g(s):\n    s.err_console.print(error('error:'), 'new')\n",
        "def g(s):\n    emit({'command': 'c', 'status': 'error', 'error': 'x'})\n",
    ],
)
def test_either_gained_fingerprint_is_rejected(repo: Path, src: str) -> None:
    (key,) = sites.sites_in_source(src, "cli/new.py")
    _gain(repo, key)
    assert _check(repo).returncode == 1
