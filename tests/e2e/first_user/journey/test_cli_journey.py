"""The CLI V1 journey (roadmap row 75): one e2e test per step of `docs/qa/cli-v1-journey.md`.

A module fixture builds a project under a temp folder, runs the steps in id order and caches each
result. Each test cites its step with `journey_step` and asserts only that step: the exit codes it
reads from the document, never from a copy here, and the Expected facts. The command each step runs
is checked against the document's own command span, so the document cannot drift from the test.

Two modes. Source (default) runs `python -m decoy`. Installed bundle runs when
`DECOY_JOURNEY_BIN` (the installed `decoy` launcher) and `DECOY_JOURNEY_HOME` (that install's
`DECOY_HOME`) are both set: a cleaned environment, a temp working folder, and a refusal to start
unless the bundle's own `decoy` and `decoy_engine` are what the install imports. Nothing falls
back to the source tree.

Every text cell of the fixture data carries `jmark` plus a number and the mask secret is 48 random
bytes. After each step a sweep looks for a marker or the secret in stdout, stderr and every file the
run made that is not data. A sweep that read nothing fails.

Mutations (each turns a named test red): make `emit_error` append the offending value (CJ-05 sweep);
drop the foreign key from the `shop` pipeline (CJ-07); run CJ-08's check before CJ-07 (order test);
point the project root at the repo (nothing-written test); fall back to `python -m decoy` when
`DECOY_JOURNEY_BIN` is missing (AT-J9); keep the caller's `PYTHONPATH`, skip the import probe, or run
a step with the checkout as cwd (AT-J12).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shlex
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import polars as pl
import pytest
import yaml
from scripts.qa import sweep as qa_sweep

from tests.cli_journey import allowed_exit_codes, journey_step, step_by_id

REPO = Path(__file__).resolve().parents[4]
BIN_VAR = "DECOY_JOURNEY_BIN"
HOME_VAR = "DECOY_JOURNEY_HOME"
SECRET_VAR = "JOURNEY_SECRET"
DROPPED_VARS = (
    "PYTHONPATH",
    "PYTHONHOME",
    "PYTHONSTARTUP",
    "PYTHONUSERBASE",
    "VIRTUAL_ENV",
    "CONDA_PREFIX",
)
CUSTOMERS = 20
ORDERS = 40
STEP_TIMEOUT_S = 180
_IGNORED_NAMES = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}


class JourneyEnvError(Exception):
    """The journey environment variables are missing or point at nothing."""


class BundleRefused(Exception):
    """The installed bundle is not what would run. The text names the failed check."""


# ---- Mode and environment ----------------------------------------------------------------------


@dataclass(frozen=True)
class Mode:
    prefix: tuple[str, ...]
    bundle_home: Path | None = None

    @property
    def is_bundle(self) -> bool:
        return self.bundle_home is not None


def select_mode(environ: Mapping[str, str]) -> Mode:
    """Source mode, or bundle mode when both variables are set and real. Never a silent fallback."""
    launcher, home = environ.get(BIN_VAR, ""), environ.get(HOME_VAR, "")
    if not launcher and not home:
        return Mode((sys.executable, "-m", "decoy"))
    if not launcher:
        raise JourneyEnvError(f"{BIN_VAR} is required when {HOME_VAR} is set")
    if not home:
        raise JourneyEnvError(f"{HOME_VAR} is required when {BIN_VAR} is set")
    if not Path(launcher).is_file():
        raise JourneyEnvError(f"{BIN_VAR} does not name a file")
    if not Path(home).is_dir():
        raise JourneyEnvError(f"{HOME_VAR} does not name a folder")
    return Mode((launcher,), Path(home))


def inside(path: Path, parent: Path) -> bool:
    return parent.resolve() == path.resolve() or parent.resolve() in path.resolve().parents


def _clean_path(path_value: str, checkout: Path) -> str:
    kept = []
    for entry in path_value.split(os.pathsep):
        if not entry:
            continue
        venv = Path(sys.prefix) if sys.prefix != sys.base_prefix else None
        if inside(Path(entry), checkout) or (venv is not None and inside(Path(entry), venv)):
            continue
        kept.append(entry)
    return os.pathsep.join(kept)


def child_env(
    caller: Mapping[str, str], *, root: Path, secret: str, checkout: Path, bundle_home: Path | None
) -> dict[str, str]:
    """The environment of every step: nothing of the caller's Python, DECOY_ or XDG_ settings."""
    env = {
        k: v
        for k, v in caller.items()
        if k not in DROPPED_VARS and not k.startswith(("DECOY_", "XDG_"))
    }
    env["PATH"] = (
        _clean_path(caller.get("PATH", ""), checkout) if bundle_home else env.get("PATH", "")
    )
    env.update(HOME=str(root / "user"), DECOY_NO_UPDATE_CHECK="1", **{SECRET_VAR: secret})
    if bundle_home is not None:
        env["DECOY_HOME"] = str(bundle_home)
    else:
        env["PYTHONPATH"] = str(checkout / "src")
    return env


def bundle_cwd(root: Path) -> Path:
    """The folder a bundle step runs in: inside the temp root, never the checkout."""
    work = root / "work"
    work.mkdir(exist_ok=True)
    return work


_PROBE = (
    "import decoy, decoy_engine; "
    "print(decoy.__file__); print(decoy_engine.__file__); print(decoy.__version__)"
)


def prove_bundle(
    launcher: Path, home: Path, env: Mapping[str, str], cwd: Path, checkout: Path
) -> None:
    """Refuse unless the install's own interpreter imports `decoy` and `decoy_engine` from the install."""
    real = launcher.resolve()
    if inside(real, checkout) or inside(real, Path(sys.prefix)):
        raise BundleRefused(
            "launcher-location: the launcher is inside the checkout or its environment"
        )
    python = home / "current" / "python" / "bin" / "python3"
    probe = subprocess.run(
        [str(python), "-I", "-c", _PROBE], env=dict(env), cwd=cwd, capture_output=True, text=True
    )
    lines = probe.stdout.splitlines()
    if probe.returncode or not lines:
        raise BundleRefused("import-location: the install's interpreter cannot import decoy")
    *files, version = lines
    for name in files:
        if inside(Path(name), checkout) or not inside(Path(name), home):
            raise BundleRefused(
                "import-location: decoy or decoy_engine is not imported from the install"
            )
    shown = subprocess.run(
        [str(launcher), "--version"], env=dict(env), cwd=cwd, capture_output=True, text=True
    )
    if version not in shown.stdout:
        raise BundleRefused(
            "version: the launcher reports another version than the install's interpreter"
        )


# ---- Sweeps and the project fixture ------------------------------------------------------------


@dataclass(frozen=True)
class Run:
    argv: tuple[str, ...]
    cwd: Path
    code: int
    out: str
    err: str


@dataclass(frozen=True)
class StepResult:
    runs: tuple[Run, ...]
    leaks: tuple[str, ...]
    swept: int

    @property
    def codes(self) -> tuple[int, ...]:
        return tuple(r.code for r in self.runs)


def _not_data(shop: Path) -> list[Path]:
    """Files a run made that are not data: evidence, vault, project and library records."""
    skip = {shop / "data", shop / "pipelines"}
    found = []
    for path in sorted(shop.rglob("*")):
        if not path.is_file() or path.suffix in {".csv", ".parquet"}:
            continue
        if any(parent in skip for parent in path.parents):
            continue
        found.append(path)
    return found


def _sweep(shop: Path, runs: list[Run], secret: str) -> tuple[tuple[str, ...], int]:
    """Look for a marker or the secret in every capture, through the one QA sweep."""
    captures: dict[str, tuple[str, bytes]] = {}
    for n, run in enumerate(runs):
        captures[f"stdout of command {n}"] = ("stdout", run.out.encode())
        captures[f"stderr of command {n}"] = ("stderr", run.err.encode())
    for path in _not_data(shop):
        # Files that are not data are not one registry surface; `logs` is the generic text one.
        captures[f"file {path.relative_to(shop).as_posix()}"] = ("logs", path.read_bytes())
    labels = ("marker", "secret", "secret bytes")
    needles = (b"jmark", secret.encode(), bytes.fromhex(secret))
    swept = sum(len(blob) for _, blob in captures.values())
    if not swept:
        return (), 0
    found = qa_sweep.sweep(captures, needles, qa_sweep.load_registry())
    return tuple(f"{labels[int(lk.coordinate[1:])]} in {lk.name}" for lk in found), swept


def _tree(path: Path, depth: int = 2) -> frozenset[str]:
    names: set[str] = set()
    try:
        entries = list(os.scandir(path))
    except OSError:
        return frozenset()
    for entry in entries:
        if entry.name in _IGNORED_NAMES:
            continue
        names.add(entry.path)
        if depth > 1 and entry.is_dir(follow_symlinks=False):
            names |= _tree(Path(entry.path), depth - 1)
    return frozenset(names)


# The home paths the CLI itself can write to if it ignored the redirected HOME. They come from
# the CLI's own path helpers: decoy_home() is ~/.decoy (src/decoy/distribution/layout.py:34) and
# launcher_bin_dir() is ~/.local/bin (layout.py:101). The whole home is not snapshotted because a
# shared test node has other jobs writing there while the suite runs, which made AT-J7 flaky.
_CLI_HOME_PATHS: tuple[tuple[str, ...], ...] = ((".decoy",), (".local", "bin"))


def _cli_home_tree(home: Path) -> frozenset[str]:
    names: set[str] = set()
    for parts in _CLI_HOME_PATHS:
        for i in range(1, len(parts)):
            parent = home.joinpath(*parts[:i])
            names.add(str(parent) if parent.exists() else "")
        target = home.joinpath(*parts)
        if target.exists():
            names.add(str(target))
            names |= _tree(target)
    return frozenset(names)


def _data_frames() -> tuple[pl.DataFrame, pl.DataFrame]:
    customers = pl.DataFrame(
        {
            "id": list(range(1, CUSTOMERS + 1)),
            "label": [f"jmark{1000 + i}" for i in range(CUSTOMERS)],
            "email": [f"jmark{2000 + i}@example.invalid" for i in range(CUSTOMERS)],
        }
    )
    orders = pl.DataFrame(
        {
            "id": list(range(1, ORDERS + 1)),
            "customer_id": [(i % CUSTOMERS) + 1 for i in range(ORDERS)],
            "note": [f"jmark{3000 + i}" for i in range(ORDERS)],
        }
    )
    return customers, orders


def _write_pipeline(shop: Path, name: str, config: dict[str, Any]) -> None:
    folder = shop / "pipelines" / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "pipeline.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")


def _pipelines(shop: Path) -> None:
    parquet = shop / "data" / "parquet"
    sources = {
        t: {"type": "file", "format": "parquet", "path": str(parquet / f"{t}.parquet")}
        for t in ("customers", "orders")
    }
    targets = {
        t: {"type": "file", "format": "csv", "path": f"{t}.csv"} for t in ("customers", "orders")
    }
    _write_pipeline(
        shop,
        "shop",
        {
            "version": 2,
            "global_settings": {"seed": 7},
            "sources": sources,
            "tables": [
                {
                    "name": "customers",
                    "columns": [
                        {"name": "id", "strategy": "hash", "namespace": "cid"},
                        {"name": "label", "strategy": "redact"},
                        {"name": "email", "strategy": "redact"},
                    ],
                },
                {
                    "name": "orders",
                    "columns": [
                        {"name": "id", "strategy": "passthrough"},
                        {"name": "customer_id", "strategy": "hash", "namespace": "cid"},
                        {"name": "note", "strategy": "redact"},
                    ],
                },
            ],
            "relationships": [
                {
                    "parent": {"table": "customers", "columns": ["id"]},
                    "children": [{"table": "orders", "columns": ["customer_id"]}],
                    "orphan_policy": "preserve",
                    "namespace": "cid",
                }
            ],
            "subset": {
                "seeds": [
                    {
                        "table": "customers",
                        "mode": "sample",
                        "key_columns": ["id"],
                        "fraction": 0.25,
                    }
                ]
            },
            "targets": targets,
        },
    )
    _write_pipeline(
        shop,
        "bad",
        {
            "version": 2,
            "bogus_key": 1,
            "global_settings": {"seed": "jmark9001"},
            "sources": {},
            "tables": [],
            "targets": {},
        },
    )
    _write_pipeline(
        shop,
        "vaulted",
        {
            "version": 2,
            "global_settings": {"seed": 7},
            "sources": {"customers": sources["customers"]},
            "tables": [
                {
                    "name": "customers",
                    "columns": [
                        {"name": "id", "strategy": "passthrough"},
                        {"name": "email", "strategy": "hash", "namespace": "em", "vault": True},
                        {"name": "label", "strategy": "redact"},
                    ],
                }
            ],
            "targets": {"customers": targets["customers"]},
        },
    )


def _digests(shop: Path) -> dict[str, str]:
    data = shop / "data"
    return {
        p.relative_to(shop).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(data.rglob("*"))
        if p.is_file()
    }


class Journey:
    """The project, the steps run so far and their cached results."""

    def __init__(self, root: Path, mode: Mode, env: dict[str, str], secret: str) -> None:
        self.root, self.mode, self.env, self.secret = root, mode, env, secret
        self.shop = root / "shop"
        self.cwd = bundle_cwd(root) if mode.is_bundle else root
        self.results: dict[str, StepResult] = {}
        self.order: list[str] = []
        self.digests: dict[str, str] = {}
        self.before: tuple[frozenset[str], frozenset[str]] = (frozenset(), frozenset())
        self.after: tuple[frozenset[str], frozenset[str]] = (frozenset(), frozenset())

    def _exec(self, argv: list[str], cwd: Path) -> Run:
        full = (*self.mode.prefix, *argv)
        done = subprocess.run(
            full, cwd=cwd, env=self.env, capture_output=True, text=True, timeout=STEP_TIMEOUT_S
        )
        return Run(tuple(argv), cwd, done.returncode, done.stdout, done.stderr)

    def step(
        self,
        step_id: str,
        argvs: list[list[str]],
        *,
        cwd: Path | None = None,
        between: Callable[[int], None] | None = None,
    ) -> None:
        """Run the step's commands, after checking each equals the document's own command span."""
        spans = step_by_id(step_id).commands
        assert len(spans) == len(argvs), f"{step_id}: the document lists {len(spans)} commands"
        runs = []
        for n, argv in enumerate(argvs):
            assert shlex.split(spans[n]) == ["decoy", *argv], (
                f"{step_id}: command {n} drifted from the document"
            )
            if between is not None and n:
                between(n)
            runs.append(self._exec(argv, cwd or self.shop))
        leaks, swept = (
            _sweep(self.shop, runs, self.secret)
            if self.shop.exists()
            else ((), sum(len(r.out + r.err) for r in runs))
        )
        self.results[step_id] = StepResult(tuple(runs), leaks, swept)
        self.order.append(step_id)

    def reuse(self, step_id: str, earlier: str) -> None:
        """A step that checks the outputs of an earlier run and does not run again."""
        argv = list(self.results[earlier].runs[0].argv)
        assert shlex.split(step_by_id(step_id).commands[0]) == ["decoy", *argv]
        self.results[step_id] = self.results[earlier]
        self.order.append(step_id)

    def json(self, step_id: str, index: int = 0) -> dict[str, Any]:
        return json.loads(self.results[step_id].runs[index].out)


def _build(root: Path, mode: Mode) -> Journey:
    secret = secrets.token_hex(48)
    env = child_env(
        os.environ, root=root, secret=secret, checkout=REPO, bundle_home=mode.bundle_home
    )
    (root / "user").mkdir()
    journey = Journey(root, mode, env, secret)
    if mode.bundle_home is not None:
        prove_bundle(Path(mode.prefix[0]), mode.bundle_home, env, journey.cwd, REPO)
    journey.before = (_cli_home_tree(Path.home()), _tree(REPO))
    ref = f"env:{SECRET_VAR}"
    mask = ["--mask-secret", ref]
    journey.step("CJ-01", [["--version"]], cwd=journey.cwd)
    journey.step("CJ-02", [["project", "new", "shop", "--json"]], cwd=journey.cwd)
    shop = journey.shop
    (shop / "data" / "parquet").mkdir(parents=True)
    customers, orders = _data_frames()
    customers.write_csv(shop / "data" / "customers.csv")
    orders.write_csv(shop / "data" / "orders.csv")
    customers.write_parquet(shop / "data" / "parquet" / "customers.parquet")
    orders.write_parquet(shop / "data" / "parquet" / "orders.parquet")
    (shop / "jout").mkdir()
    _pipelines(shop)
    journey.digests = _digests(shop)
    journey.step("CJ-03", [["init", "customers", "--source", "data/customers.csv", "--json", "-y"]])
    journey.step(
        "CJ-04", [["scan", "data/customers.csv", "data/orders.csv", "--has-header", "--json"]]
    )
    journey.step("CJ-05", [["validate", "bad", "--json"]])
    journey.step("CJ-06", [["validate", "shop"]])
    shop_run = [
        "run",
        "shop",
        *mask,
        "--out-dir",
        "jout/shop",
        "--evidence-out",
        "jout/shop-evidence.json",
        "--json",
    ]
    journey.step("CJ-07", [shop_run])
    journey.reuse("CJ-08", "CJ-07")
    journey.step(
        "CJ-09",
        [
            [
                "report",
                "integrity",
                "jout/shop/customers.csv",
                "--source",
                "data/customers.csv",
                "--config",
                "shop",
                "--allow-source-mismatch",
                "--json",
            ]
        ],
    )
    orders_out = shop / "jout" / "shop" / "orders.csv"
    # A failed CJ-07 leaves no file; the CJ-07 and CJ-10 tests then fail on their own exits.
    original = orders_out.read_bytes() if orders_out.exists() else b""

    def change_one_byte(_: int) -> None:
        if original:
            orders_out.write_bytes(original[:-2] + b"X" + original[-1:])

    verify = ["report", "verify", "jout/shop-evidence.json", "--json"]
    journey.step("CJ-10", [verify, verify], between=change_one_byte)
    if original:
        orders_out.write_bytes(original)
    journey.step(
        "CJ-11",
        [
            [
                "run",
                "vaulted",
                *mask,
                "--vault",
                "jout/vault.bin",
                "--out-dir",
                "jout/vaulted",
                "--json",
            ],
            [
                "unmask",
                "pipelines/vaulted/pipeline.yaml",
                "jout/vaulted/customers.csv",
                *mask,
                "--vault",
                "jout/vault.bin",
                "-o",
                "jout/customers.unmasked.csv",
                "--json",
            ],
        ],
    )
    (shop / "jout" / "strict" / "orders.csv").mkdir(parents=True)
    journey.step("CJ-12", [["run", "shop", *mask, "--out-dir", "jout/strict", "--json"]])
    journey.after = (_cli_home_tree(Path.home()), _tree(REPO))
    return journey


@pytest.fixture(scope="module")
def journey(tmp_path_factory: pytest.TempPathFactory) -> Journey:
    try:
        mode = select_mode(os.environ)
    except JourneyEnvError as err:
        pytest.fail(str(err), pytrace=False)
    try:
        return _build(tmp_path_factory.mktemp("journey"), mode)
    except BundleRefused as err:
        pytest.fail(f"installed bundle refused: {err}", pytrace=False)


def checked(journey: Journey, step_id: str) -> StepResult:
    """The step's result after its shared checks: exits from the document, a clean non-empty sweep."""
    step = step_by_id(step_id)
    result = journey.results[step_id]
    assert result.codes == step.exits, f"{step_id}: exit codes differ from the document"
    assert set(step.exits) <= allowed_exit_codes()
    assert result.leaks == (), f"{step_id}: a marker or the secret reached {result.leaks}"
    assert result.swept > 0, f"{step_id}: the sweep read nothing"
    return result


def _csv(shop: Path, rel: str) -> pd.DataFrame:
    return pd.read_csv(shop / rel, dtype=str)


# ---- The steps ---------------------------------------------------------------------------------


@journey_step("CJ-01")
def test_cj01_version(journey: Journey) -> None:
    result = checked(journey, "CJ-01")
    assert re.fullmatch(r"decoy \d+(?:\.\d+)+\S*", result.runs[0].out.strip())


@journey_step("CJ-02")
def test_cj02_project_new(journey: Journey) -> None:
    payload = json.loads(checked(journey, "CJ-02").runs[0].out)
    assert Path(payload["root"]).resolve() == journey.shop.resolve()
    assert payload["already_project"] is False
    for folder in ("pipelines", "out", ".decoy"):
        assert (journey.shop / folder).is_dir()


@journey_step("CJ-03")
def test_cj03_init_from_file(journey: Journey) -> None:
    payload = json.loads(checked(journey, "CJ-03").runs[0].out)
    assert payload["status"] == "ok" and payload["name"] == "customers"
    assert payload["source"] == "data/customers.csv"
    assert payload["column_count"] == len(_data_frames()[0].columns)
    written = journey.shop / "pipelines" / "customers" / "pipeline.yaml"
    columns = [c for t in yaml.safe_load(written.read_text())["tables"] for c in t["columns"]]
    assert [c["name"] for c in columns] == _data_frames()[0].columns
    assert all(c["strategy"] for c in columns), "a column has no starter strategy"


@journey_step("CJ-04")
def test_cj04_scan(journey: Journey) -> None:
    payload = json.loads(checked(journey, "CJ-04").runs[0].out)
    tables = {t["name"]: t for t in payload["tables"]}
    assert set(tables) == {"customers", "orders"}
    assert (tables["customers"]["row_count"], tables["orders"]["row_count"]) == (CUSTOMERS, ORDERS)
    for name, table in tables.items():
        assert table["field_count"] == len(_data_frames()[name == "orders"].columns)
        assert 0 <= table["reid_risk_score"] <= 1
    assert tables["customers"]["pii_candidate_count"] >= 1, "the email column is a candidate"
    assert "SUGGESTIONS" in payload["pii_note"]


@journey_step("CJ-05")
def test_cj05_bad_pipeline_refused(journey: Journey) -> None:
    payload = json.loads(checked(journey, "CJ-05").runs[0].out)
    assert set(payload) == {"command", "status", "config", "messages"}
    assert payload["status"] == "error"
    found = {(m["location"], m["code"]) for m in payload["messages"]}
    assert ("bogus_key", "extra_forbidden") in found
    assert ("global_settings.seed", "int_parsing") in found
    made = [p.name for p in (journey.shop / "out").iterdir() if p.name != ".gitignore"]
    assert made == [], "a refused validation made a run folder"


@journey_step("CJ-06")
def test_cj06_validate_passes(journey: Journey) -> None:
    out = checked(journey, "CJ-06").runs[0].out
    for layer in ("Config", "Compile", "Preflight"):
        assert f"{layer}: passed" in out


@journey_step("CJ-07")
def test_cj07_subset_run(journey: Journey) -> None:
    payload = json.loads(checked(journey, "CJ-07").runs[0].out)
    subset = payload["subset"]
    assert subset["applied"] is True
    counts = subset["tables"]
    assert counts["customers"]["source_rows"] == CUSTOMERS
    assert 0 < counts["customers"]["kept_rows"] < CUSTOMERS
    assert counts["orders"]["source_rows"] == ORDERS
    assert 0 < counts["orders"]["kept_rows"] < ORDERS
    assert (journey.shop / "jout" / "shop-evidence.json").is_file()
    customers, orders = (
        _csv(journey.shop, "jout/shop/customers.csv"),
        _csv(journey.shop, "jout/shop/orders.csv"),
    )
    assert len(customers) == counts["customers"]["kept_rows"]
    assert len(orders) == counts["orders"]["kept_rows"]
    assert set(orders["customer_id"]) <= set(customers["id"]), "a kept order lost its parent"


@journey_step("CJ-08")
def test_cj08_masked_outputs(journey: Journey) -> None:
    assert journey.order.index("CJ-07") < journey.order.index("CJ-08"), "CJ-08 checks CJ-07's run"
    checked(journey, "CJ-08")
    kept = json.loads(journey.results["CJ-08"].runs[0].out)["subset"]["tables"]
    for table, source in (("customers", "customers"), ("orders", "orders")):
        masked, original = (
            _csv(journey.shop, f"jout/shop/{table}.csv"),
            _csv(journey.shop, f"data/{source}.csv"),
        )
        assert len(masked) == kept[table]["kept_rows"]
        changed = {"customers": ["id", "label", "email"], "orders": ["customer_id", "note"]}[table]
        for column in changed:
            assert not set(masked[column]) & set(original[column]), (
                f"{table}.{column} was not masked"
            )
    orders_in, orders_out = (
        _csv(journey.shop, "data/orders.csv"),
        _csv(journey.shop, "jout/shop/orders.csv"),
    )
    assert set(orders_out["id"]) <= set(orders_in["id"]), "the passthrough column changed"
    assert _digests(journey.shop) == journey.digests, "an input file changed"


@journey_step("CJ-09")
def test_cj09_post_scan(journey: Journey) -> None:
    payload = json.loads(checked(journey, "CJ-09").runs[0].out)
    assert payload["status"] == "ok"
    assert payload["report"]["residual_pii"] == []


@journey_step("CJ-10")
def test_cj10_evidence_verify(journey: Journey) -> None:
    result = checked(journey, "CJ-10")
    first, second = (json.loads(r.out) for r in result.runs)
    assert first["status"] == "ok" and first["issue_count"] == 0
    assert second["status"] == "fingerprint_mismatch"
    assert any("jout/shop/orders.csv" in issue for issue in second["issues"])


@journey_step("CJ-11")
def test_cj11_vault_round_trip(journey: Journey) -> None:
    result = checked(journey, "CJ-11")
    assert json.loads(result.runs[0].out)["status"] == "ok"
    assert json.loads(result.runs[1].out)["status"] == "ok"
    recovered = _csv(journey.shop, "jout/customers.unmasked.csv")
    original = _csv(journey.shop, "data/customers.csv")
    assert recovered["email"].tolist() == original["email"].tolist()
    assert (
        _csv(journey.shop, "jout/vaulted/customers.csv")["email"].tolist()
        != original["email"].tolist()
    )


def test_cj12_the_failed_run_is_reported(journey: Journey) -> None:
    """The part of CJ-12 that holds on main, so the strict xfail below cannot hide a broken setup."""
    result = checked(journey, "CJ-12")
    payload = json.loads(result.runs[0].out)
    assert payload["status"] == "error"
    assert (journey.shop / "jout" / "strict" / "orders.csv").is_dir(), "the blocker was removed"


@journey_step("CJ-12")
def test_cj12_strict_delivery(journey: Journey) -> None:
    """Only the strict-delivery facts: nothing delivered, and the error names the table and a code."""
    strict = journey.shop / "jout" / "strict"
    left = sorted(p.relative_to(strict).as_posix() for p in strict.rglob("*") if p.is_file())
    assert left == [], "a target file of the failed run was left behind"
    payload = json.loads(journey.results["CJ-12"].runs[0].out)
    assert "orders" in json.dumps(payload["error"]) and payload["reason"]["code"]


# ---- The harness itself ------------------------------------------------------------------------


def test_nothing_is_written_outside_the_temp_root(journey: Journey) -> None:
    """AT-J7: the repo and the real $HOME gained nothing, and no step ran outside the temp root."""
    assert journey.after == journey.before
    runs = [r for result in journey.results.values() for r in result.runs]
    assert runs and all(inside(r.cwd, journey.root) for r in runs)
    assert journey.shop.resolve() != REPO.resolve() and not inside(journey.shop, REPO)


@pytest.mark.parametrize("parts", _CLI_HOME_PATHS)
def test_home_snapshot_catches_a_write_to_a_cli_home_path(
    parts: tuple[str, ...], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Seeded mutation for AT-J7: a file in a CLI home path changes the snapshot, noise elsewhere does not."""
    monkeypatch.setenv("HOME", str(tmp_path))
    before = _cli_home_tree(Path.home())
    (tmp_path / "decoy").mkdir()
    (tmp_path / "decoy" / "vmrun-1").write_text("other job")
    assert _cli_home_tree(Path.home()) == before
    leaf = tmp_path.joinpath(*parts)
    leaf.mkdir(parents=True)
    assert _cli_home_tree(Path.home()) != before
    mid = _cli_home_tree(Path.home())
    (leaf / "stray").write_text("x")
    assert _cli_home_tree(Path.home()) != mid


def test_missing_journey_variables_name_the_variable(tmp_path: Path) -> None:
    """AT-J9: a bad bundle setting is an error naming the variable, never source mode."""
    launcher = tmp_path / "decoy"
    launcher.write_text("#!/bin/sh\n")
    with pytest.raises(JourneyEnvError, match=BIN_VAR):
        select_mode({BIN_VAR: str(tmp_path / "missing"), HOME_VAR: str(tmp_path)})
    with pytest.raises(JourneyEnvError, match=HOME_VAR):
        select_mode({BIN_VAR: str(launcher)})
    with pytest.raises(JourneyEnvError, match=BIN_VAR):
        select_mode({HOME_VAR: str(tmp_path)})
    with pytest.raises(JourneyEnvError, match=HOME_VAR):
        select_mode({BIN_VAR: str(launcher), HOME_VAR: str(tmp_path / "missing")})
    assert not select_mode({}).is_bundle
    assert select_mode({BIN_VAR: str(launcher), HOME_VAR: str(tmp_path)}).is_bundle


def test_bundle_mode_refuses_the_checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AT-J12: a launcher that runs the checkout's interpreter is refused, naming the import check."""
    home = tmp_path / "home"
    python = home / "current" / "python" / "bin" / "python3"
    python.parent.mkdir(parents=True)
    python.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
    launcher = tmp_path / "bin" / "decoy"
    launcher.parent.mkdir()
    launcher.write_text(f'#!/bin/sh\nexec "{python}" -m decoy "$@"\n')
    for script in (python, launcher):
        script.chmod(0o755)
    monkeypatch.setenv("PYTHONPATH", str(REPO / "src"))
    monkeypatch.setenv("VIRTUAL_ENV", sys.prefix)
    monkeypatch.chdir(REPO)
    root = tmp_path / "root"
    root.mkdir()
    env = child_env(os.environ, root=root, secret="00" * 48, checkout=REPO, bundle_home=home)
    assert not {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"} & set(env)
    assert not any(inside(Path(p), REPO) for p in env["PATH"].split(os.pathsep) if p)
    cwd = bundle_cwd(root)
    assert inside(cwd, root) and not inside(cwd, REPO)
    with pytest.raises(BundleRefused, match="import-location"):
        prove_bundle(launcher, home, env, cwd, REPO)
