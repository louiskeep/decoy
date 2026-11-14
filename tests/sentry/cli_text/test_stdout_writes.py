"""G-ONE-JSON-STDOUT: a CLI command writes JSON to stdout only through `ui/output.py`.

`emit_json` (the `--json` envelope) and `emit_json_document` (a raw document in default mode) are
the two writers. A third one drifts on flush, newline and mode checks: the streamed scan once
wrote its document by hand, and a refactor to `emit_json` would have printed nothing. The scan
lives in `_stdout_sites.py`.

Two contracts. `OUTPUT_WRITERS` pins the writers in `ui/output.py`, exactly one write each, so
a third write there fails. Every write elsewhere is the shrink-only baseline
`baselines/json-stdout-writes.json` (one legacy site today), keyed per write with an ordinal;
the ratchet rejects an added key and `test_baseline_registry.py` ties it to the live scan.
"""

from __future__ import annotations

import json

from tests.sentry.cli_text import _stdout_sites as sites

BASELINE = sites.ROOT / "tests" / "sentry" / "baselines" / "json-stdout-writes.json"
REGISTRY = sites.ROOT / "scripts" / "dev" / "sentry_registry.toml"

OUTPUT_WRITERS = frozenset({"ui/output.py::emit_json::1", "ui/output.py::emit_json_document::1"})


def _recorded() -> set[str]:
    return set(json.loads(BASELINE.read_text(encoding="utf-8"))["entries"])


def test_the_output_module_holds_exactly_the_two_writers() -> None:
    live = {k for k in sites.all_sites() if k.startswith(f"{sites.OUTPUT_MODULE}::")}
    assert live == OUTPUT_WRITERS


def test_baseline_equals_the_source_inventory() -> None:
    live, recorded = sites.inventory(), _recorded()
    assert live - recorded == set(), "JSON stdout writes outside ui/output.py (use its writers)"
    assert recorded - live == set(), "stale baseline entries (shrink the baseline)"


def test_baseline_holds_no_output_module_row() -> None:
    assert not any(k.startswith(f"{sites.OUTPUT_MODULE}::") for k in _recorded())


def test_baseline_is_registered_as_cl2() -> None:
    doc = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert doc["sentry_id"] == "json-stdout-writes"
    assert doc["created_in"] == "CL2"
    assert 'id = "json-stdout-writes"' in REGISTRY.read_text(encoding="utf-8")


# --- seeded spellings: each turns the scan red --------------------------------------------

_SEEDS = {
    "write": "import sys, json\ndef f(x):\n    sys.stdout.write(json.dumps(x))\n",
    "print": "import json\ndef f(x):\n    print(json.dumps(x))\n",
    "echo": "import json as _json, typer\ndef f(x):\n    typer.echo(_json.dumps(x))\n",
    "named": 'import sys, json\ndef f(x):\n    s = json.dumps(x)\n    sys.stdout.write(s + "\\n")\n',
    "from_import": "from json import dumps as d\nimport sys\ndef f(x):\n    sys.stdout.write(d(x))\n",
    "dump": "import json, sys\ndef f(x):\n    json.dump(x, sys.stdout)\n",
    "stdout_alias": "from sys import stdout\nimport json\ndef f(x):\n    stdout.write(json.dumps(x))\n",
    "print_stdout": "import json, sys\ndef f(x):\n    print(json.dumps(x), file=sys.stdout)\n",
}


def test_each_seeded_spelling_is_seen() -> None:
    for name, source in _SEEDS.items():
        assert sites.sites_in_source(source, f"{name}.py") == {f"{name}.py::f::1"}, name


def test_a_second_write_in_one_function_is_a_new_key() -> None:
    source = "import sys, json\ndef f(x):\n    sys.stdout.write(json.dumps(x))\n    print(json.dumps(x))\n"
    assert sites.sites_in_source(source, "a.py") == {"a.py::f::1", "a.py::f::2"}


def test_stderr_and_non_json_writes_are_not_sites() -> None:
    source = (
        "import sys, json, typer\n"
        "def f(x):\n"
        "    sys.stdout.write('text')\n"
        "    typer.echo(json.dumps(x), err=True)\n"
        "    print(json.dumps(x), file=sys.stderr)\n"
        "    json.dump(x, sys.stderr)\n"
        "    s = json.dumps(x)\n"
        "    return s\n"
    )
    assert sites.sites_in_source(source, "ok.py") == set()
