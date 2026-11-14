"""Sentry: the CLI's import layers hold, and the layer list is the reviewed one.

``.importlinter`` declares one import-linter ``layers`` contract over the top-level children
of ``decoy``. It is exhaustive, so a new top-level package or module is red until it is
placed. ``LAYERS`` below is the reviewed snapshot of the tiers: config and snapshot must agree
exactly, so placing a package or moving one down a tier edits both in the same diff. The
ignore lines are measured back imports that exist today; they may only shrink (X0a baseline
``import-layers``, keyed ``layers::<importer> -> <imported>``).

The flat ``cli`` package is frozen (``test_package_fanout.py``); it sits in its tier whole.

This file runs only in the isolated ``layers`` gate step (``scripts/dev/gates.sh --steps
layers``), which bootstraps ``.venv-layers`` from ``requirements-dev.lock``; every other route
ignores this path. import-linter is imported inside the test functions, so collecting this
file anywhere works, and running it without the dependency fails with install advice instead
of skipping.
"""

from __future__ import annotations

import ast
import configparser
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from tests.sentry.layout import ignore_keys, map_paths

ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / ".importlinter"
CONTRACT = "layers"
INSTALL = (
    "import-linter is not installed in this venv. Run `scripts/dev/gates.sh --steps layers`, "
    "which bootstraps .venv-layers from requirements-dev.lock."
)

# Reviewed snapshot of the tiers in .importlinter, top to bottom; `:` siblings may import each
# other, `|` siblings may not. Edit it in the same diff as the config.
LAYERS: tuple[str, ...] = (
    "__main__",
    "api",
    "cli : _update_check",
    "ci | _resources",
    "ui | distribution | notify | telemetry | templates",
    "_mask_secret | _mask_secret_guidance | _native_gate | _atomic | _row_sample | _env_flags",
    "_config_file",
    "_private_file | _version | _yaml_errors",
)


def config_layers(text: str) -> tuple[str, ...]:
    """The tier lines of the contract, whitespace-normalised."""
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.read_string(text)
    raw = parser.get(f"importlinter:contract:{CONTRACT}", "layers")
    return tuple(" ".join(line.split()) for line in raw.splitlines() if line.strip())


def _lint_api() -> Callable[..., bool]:
    try:
        from importlinter.application.use_cases import lint_imports
        from importlinter.configuration import configure
    except ImportError:
        pytest.fail(INSTALL)
    configure()
    return lint_imports


def test_the_layer_contract_is_kept() -> None:
    lint_imports = _lint_api()
    kept = lint_imports(config_filename=str(CONFIG), cache_dir=None, no_logo=True)
    assert kept, "the import-layer contract is broken; the import-linter report is above"


def test_config_layers_equal_the_reviewed_snapshot() -> None:
    assert config_layers(CONFIG.read_text(encoding="utf-8")) == LAYERS


def facade_ignores(text: str, src: Path) -> list[str]:
    """Ignore lines whose importer or imported side is a package rather than a leaf module.

    import-linter exempts a whole module edge, not the symbols that first needed it, so an
    ignore on a package facade lets any later import through that facade.
    """
    return sorted(
        key
        for key in ignore_keys(text)
        if any((src / Path(*side.split("."))).is_dir() for side in key.split(" -> "))
    )


# The facade ignores that stay, each with the only names it may carry. cli.io and cli.gate keep
# their modules private to outside callers (cli.io: tests/sentry/test_scan_reader.py,
# io_policy/test_layout_errors.py), so these edges cannot name a leaf; this list is the
# symbol-level check import-linter lacks.
FACADE_NAMES: dict[str, frozenset[str]] = {
    "decoy.ci.adapters -> decoy.cli.gate": frozenset(
        {"gate_exit_code", "run_config_gate", "run_gate"}
    ),
    "decoy.ci.adapters -> decoy.cli.io": frozenset({"load_scan_set", "select_table"}),
    "decoy.ci.rule_codes -> decoy.cli.io": frozenset({"GATE_CODES"}),
}


def facade_names(src: Path, key: str) -> set[str]:
    """Every name the importer of ``key`` takes from the imported facade.

    Binding the facade module itself (``import a.b`` or ``from a import b``) counts as ``*``: its
    attributes cannot be listed.
    """
    importer, imported = key.split(" -> ")
    path = src / Path(*importer.split("."))
    path = path / "__init__.py" if path.is_dir() else path.with_suffix(".py")
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module == imported:
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            if any(f"{node.module}.{a.name}" == imported for a in node.names):
                names.add("*")
        elif isinstance(node, ast.Import) and any(a.name == imported for a in node.names):
            names.add("*")
    return names


def test_only_the_listed_facade_ignores_remain() -> None:
    assert facade_ignores(CONFIG.read_text(encoding="utf-8"), ROOT / "src") == sorted(FACADE_NAMES)


@pytest.mark.parametrize("key", sorted(FACADE_NAMES))
def test_a_facade_ignore_carries_only_its_listed_names(key: str) -> None:
    assert facade_names(ROOT / "src", key) == FACADE_NAMES[key]


# --- meta-tests: the guard fails closed and sees seeded violations -------------------------


def test_a_missing_import_linter_fails_with_install_advice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # None in sys.modules makes an import raise ImportError; cached submodules need it too.
    for name in ["importlinter", *(m for m in sys.modules if m.startswith("importlinter."))]:
        monkeypatch.setitem(sys.modules, name, None)
    with pytest.raises(pytest.fail.Exception, match=r"gates\.sh --steps layers"):
        _lint_api()


def test_import_linter_is_imported_only_inside_functions() -> None:
    """Collection must work in a venv without import-linter."""
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    top = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    names = [a.name for n in top for a in n.names] + [
        n.module or "" for n in top if isinstance(n, ast.ImportFrom)
    ]
    assert not [n for n in names if n.startswith("importlinter")]


_PROBE = """
import importlib.util, json, sys
from importlinter.configuration import configure
configure()
from importlinter.application.use_cases import lint_imports
origin = importlib.util.find_spec("decoy").origin
kept = lint_imports(config_filename=sys.argv[1], cache_dir=None, no_logo=True)
print("PROBE " + json.dumps({"origin": origin, "kept": kept}))
"""


@pytest.fixture(scope="module")
def scratch(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A pristine copy of the package source and config; each case copies it again."""
    base = tmp_path_factory.mktemp("layers-base")
    shutil.copytree(
        ROOT / "src" / "decoy",
        base / "src" / "decoy",
        ignore=shutil.ignore_patterns("__pycache__", "*.so", "*.pyd"),
    )
    shutil.copy(CONFIG, base / ".importlinter")
    return base


def _tree(scratch: Path, tmp_path: Path) -> Path:
    tree = tmp_path / "tree"
    shutil.copytree(scratch, tree)
    return tree


def lint_scratch(tree: Path) -> bool:
    """Lint ``tree`` in a fresh interpreter that can only see the scratch package."""
    _lint_api()  # fail with install advice before spawning anything
    env = {**os.environ, "PYTHONPATH": str(tree / "src")}
    res = subprocess.run(
        [sys.executable, "-c", _PROBE, str(tree / ".importlinter")],
        cwd=tree,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    lines = [ln for ln in res.stdout.splitlines() if ln.startswith("PROBE ")]
    assert lines, f"probe printed no result (rc {res.returncode}): {res.stderr[-2000:]}"
    result = json.loads(lines[-1].removeprefix("PROBE "))
    assert Path(result["origin"]).resolve().is_relative_to(tree.resolve()), result["origin"]
    return bool(result["kept"])


def _edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"{old!r} is not unique in {path.name}"
    path.write_text(text.replace(old, new), encoding="utf-8")


def _append(path: Path, line: str) -> None:
    path.write_text(path.read_text(encoding="utf-8") + f"\n{line}\n", encoding="utf-8")


def _snapshot_with(text: str, layers: tuple[str, ...]) -> bool:
    return config_layers(text) == layers


def test_the_facade_check_sees_a_package_ignore() -> None:
    text = "[c]\nignore_imports =\n    decoy.ci.staged -> decoy.cli.gate\n"
    assert facade_ignores(text, ROOT / "src") == ["decoy.ci.staged -> decoy.cli.gate"]


@pytest.mark.parametrize(
    ("line", "extra"),
    [
        ("from decoy.cli.io import RunLayout", {"RunLayout"}),
        ("import decoy.cli.io", {"*"}),
        ("from decoy.cli import io as _io", {"*"}),
    ],
)
def test_a_new_name_through_an_exempt_facade_is_red(
    scratch: Path, tmp_path: Path, line: str, extra: set[str]
) -> None:
    """import-linter keeps the edge (it is exempt); the name check is what goes red."""
    tree = _tree(scratch, tmp_path)
    _append(tree / "src" / "decoy" / "ci" / "adapters.py", line)
    key = "decoy.ci.adapters -> decoy.cli.io"
    assert facade_names(tree / "src", key) == FACADE_NAMES[key] | extra


@pytest.mark.parametrize(
    ("module", "line"),
    [
        # ci.runner reaching up into cli through the gate facade; only its exit_codes edge is exempt.
        ("ci/runner.py", "from decoy.cli.gate import GateResult"),
        # A child reaching the root facade, which re-exports the whole library API lazily.
        ("ui/banner.py", "from decoy import __version__ as _root_version"),
    ],
)
def test_an_upward_import_through_a_facade_is_red(
    scratch: Path, tmp_path: Path, module: str, line: str
) -> None:
    """Neither importer has a facade exemption for these edges (banner's root one is gone)."""
    tree = _tree(scratch, tmp_path)
    _append(tree / "src" / "decoy" / module, line)
    assert not lint_scratch(tree)


def test_the_pristine_scratch_copy_is_kept(scratch: Path, tmp_path: Path) -> None:
    assert lint_scratch(_tree(scratch, tmp_path))


def test_removing_one_ignore_line_is_red(scratch: Path, tmp_path: Path) -> None:
    tree = _tree(scratch, tmp_path)
    _edit(tree / ".importlinter", "    decoy.ui.output -> decoy.cli.exit_codes\n", "")
    assert not lint_scratch(tree)


def test_a_bottom_tier_module_importing_cli_is_red(scratch: Path, tmp_path: Path) -> None:
    tree = _tree(scratch, tmp_path)
    _append(tree / "src" / "decoy" / "_row_sample.py", "from decoy.cli import exit_codes")
    assert not lint_scratch(tree)


def test_an_independent_sibling_import_is_red(scratch: Path, tmp_path: Path) -> None:
    """``|`` siblings may not import each other: telemetry reaching notify is red."""
    tree = _tree(scratch, tmp_path)
    _append(tree / "src" / "decoy" / "telemetry.py", "import decoy.notify")
    assert not lint_scratch(tree)


def test_an_unplaced_top_level_package_is_red(scratch: Path, tmp_path: Path) -> None:
    tree = _tree(scratch, tmp_path)
    (tree / "src" / "decoy" / "newpkg").mkdir()
    (tree / "src" / "decoy" / "newpkg" / "__init__.py").write_text("", encoding="utf-8")
    assert not lint_scratch(tree)


def test_an_ignore_line_matching_no_import_is_red(scratch: Path, tmp_path: Path) -> None:
    tree = _tree(scratch, tmp_path)
    _edit(
        tree / ".importlinter",
        "ignore_imports =\n",
        "ignore_imports =\n    decoy._row_sample -> decoy.api\n",
    )
    assert not lint_scratch(tree)


def test_a_reviewed_new_package_goes_green_only_with_its_snapshot(
    scratch: Path, tmp_path: Path
) -> None:
    """AT-5(e): a placed package plus its CODEMAP row is green and needs no new X0a key."""
    tree = _tree(scratch, tmp_path)
    pkg = tree / "src" / "decoy" / "_probe_leaf"
    pkg.mkdir()
    (pkg / "__init__.py").write_text('"""A reviewed bottom-tier leaf."""\n', encoding="utf-8")
    cfg = tree / ".importlinter"
    before = ignore_keys(cfg.read_text(encoding="utf-8"))
    _edit(
        cfg,
        "    _private_file | _version | _yaml_errors\n",
        "    _private_file | _version | _yaml_errors | _probe_leaf\n",
    )
    assert lint_scratch(tree)
    text = cfg.read_text(encoding="utf-8")
    assert ignore_keys(text) == before
    assert not _snapshot_with(text, LAYERS), "a config edit without its snapshot must be red"
    reviewed = (*LAYERS[:-1], LAYERS[-1] + " | _probe_leaf")
    assert _snapshot_with(text, reviewed)
    row = (
        "| Probe leaf | `src/decoy/_probe_leaf/` | `src/decoy/_probe_leaf/__init__.py`"
        " | owning surface tests | bottom layer in `./.importlinter` |\n"
    )
    assert map_paths(row, tree, (1, 2, 3, 4)) == []
    assert map_paths(row.replace("_probe_leaf", "_unbuilt_leaf"), tree, (1, 2, 3, 4))


def test_a_downward_tier_move_goes_green_only_with_its_snapshot(
    scratch: Path, tmp_path: Path
) -> None:
    """AT-5(e): ``notify`` moves from tier 5 to tier 6; no new X0a key."""
    tree = _tree(scratch, tmp_path)
    cfg = tree / ".importlinter"
    before = ignore_keys(cfg.read_text(encoding="utf-8"))
    _edit(cfg, " | notify | telemetry", " | telemetry")
    _edit(cfg, " | _row_sample | _env_flags\n", " | _row_sample | _env_flags | notify\n")
    assert lint_scratch(tree)
    text = cfg.read_text(encoding="utf-8")
    assert ignore_keys(text) == before
    assert not _snapshot_with(text, LAYERS), "a config edit without its snapshot must be red"
    moved = list(LAYERS)
    moved[4] = moved[4].replace(" | notify", "")
    moved[5] += " | notify"
    assert _snapshot_with(text, tuple(moved))
