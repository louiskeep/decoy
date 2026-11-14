"""G-ONE-ENV-FLAG: the CLI reads environment switches only through `decoy._env_flags`.

Two spellings of one switch drift: `CI=false` once counted as CI and `NO_COLOR=` (empty) once
turned colour off, each because a site tested truthiness or `is not None` itself. Every read of
`os.environ` or `os.getenv` under `src/decoy` outside `_env_flags.py` is a site. The scan lives in
`_env_read_sites.py`. Today's 14 sites read a path, a URL, a secret or a number, not a switch;
they are the shrink-only baseline `baselines/env-reads.json`, keyed per read with an ordinal, so
a second read in an allowed function is a new key. The ratchet (`scripts/dev/ratchet_check.py`)
rejects a key added to the baseline; `test_baseline_registry.py` ties it to the live scan.
"""

from __future__ import annotations

import json

from tests.sentry.io_policy import _env_read_sites as sites

BASELINE = sites.ROOT / "tests" / "sentry" / "baselines" / "env-reads.json"
REGISTRY = sites.ROOT / "scripts" / "dev" / "sentry_registry.toml"


def _recorded() -> set[str]:
    return set(json.loads(BASELINE.read_text(encoding="utf-8"))["entries"])


def test_baseline_equals_the_source_inventory() -> None:
    live, recorded = sites.inventory(), _recorded()
    assert live - recorded == set(), "environment reads outside the baseline (use decoy._env_flags)"
    assert recorded - live == set(), "stale baseline entries (shrink the baseline)"


def test_baseline_is_registered_as_cl2() -> None:
    doc = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert doc["sentry_id"] == "env-reads"
    assert doc["created_in"] == "CL2"
    assert 'id = "env-reads"' in REGISTRY.read_text(encoding="utf-8")


def test_the_flag_module_exists_and_reads_the_environment() -> None:
    source = (sites.SRC / sites.OWNER).read_text(encoding="utf-8")
    assert sites.sites_in_source(source, sites.OWNER), "the owner no longer reads the environment"


# --- seeded spellings: each turns the scan red --------------------------------------------

_SEEDS = {
    "equals": 'import os\ndef f():\n    return os.environ.get("X") == "1"\n',
    "getenv": 'import os\ndef f():\n    return os.getenv("X", "0") in {"1"}\n',
    "subscript": 'import os\ndef f():\n    return os.environ["X"].strip().lower() == "true"\n',
    "aliased": 'from os import environ as e\ndef f():\n    return e.get("X") != "0"\n',
    "from_getenv": 'from os import getenv as g\ndef f():\n    return g("X")\n',
    "bool": 'import os\ndef f():\n    return bool(os.environ.get("X"))\n',
    "no_color": 'import os\ndef f():\n    return os.environ.get("NO_COLOR") is not None\n',
    "ci": 'import os\ndef f():\n    if os.environ.get("CI"):\n        return 1\n',
    "dynamic": "import os\ndef f(n):\n    return os.environ.get(n)\n",
}


def test_each_seeded_spelling_is_seen() -> None:
    for name, source in _SEEDS.items():
        assert len(sites.sites_in_source(source, f"{name}.py")) == 1, name


def test_a_second_read_in_one_function_is_a_new_key() -> None:
    source = 'import os\ndef f():\n    a = os.environ.get("X")\n    return a, os.environ.get("X")\n'
    assert sites.sites_in_source(source, "a.py") == {"a.py::f::X::1", "a.py::f::X::2"}


def test_non_reads_are_not_sites() -> None:
    source = 'import os\ndef f():\n    return "X" in os.environ and dict(os.environ)\n'
    assert sites.sites_in_source(source, "a.py") == set()


def test_a_baseline_key_not_in_the_source_is_stale() -> None:
    assert _recorded() | {"gone.py::f::X::1"} != sites.inventory()
