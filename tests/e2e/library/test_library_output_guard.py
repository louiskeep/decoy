"""The record library root is one more destination in the output-collision rule (LIB L3a).

A run stores its records under the resolved library root, so every file the run writes
(`run_outputs`) is held off that root in both directions: an output at or inside the root, and an
output above it (the root would sit inside the output). The gate refuses with the usual collision
refusal before anything is written. The matrix is one row per output kind and one column per
relation; a root that cannot be resolved never fails the run (plan L3a Rule 3).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest import mock

import pytest
import yaml

from decoy.cli.exit_codes import EXIT_OK, EXIT_RUNTIME, EXIT_USAGE
from decoy.cli.io import DECOY_DIR
from tests.e2e.library.test_run_evidence_records import (
    PIPELINE,
    _run,
    project,  # noqa: F401  (fixture)
)
from tests.keyed_secret import TEST_MASK_SECRET_REF

pytestmark = pytest.mark.usefixtures("mask_secret")
SYMLINKS = pytest.mark.skipif(os.name == "nt", reason="needs symlinks")
COLLISION = "resolve to one destination"
LIBRARY = "the record library"
IMPLICIT = "the integrity report"
KINDS = [
    "target",
    "chunked",
    "quarantine",
    "integrity-explicit",
    "integrity-implicit",
    "result",
    "evidence",
    "vault",
]
LABELS = {
    "target": "targets.customers.path",
    "chunked": "targets.customers.path",
    "quarantine": "quarantine.output_path",
    "integrity-explicit": "--integrity-out",
    "integrity-implicit": IMPLICIT,
    "result": "--result",
    "evidence": "--evidence-out",
    "vault": "--vault",
}
FLAGS = {
    "integrity-explicit": "--integrity-out",
    "result": "--result",
    "evidence": "--evidence-out",
    "vault": "--vault",
}


def _edit(project: Path, change) -> None:  # noqa: F811
    path = project / PIPELINE
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(config)
    path.write_text(yaml.safe_dump(config), encoding="utf-8")


def _keyed(*, vault: bool):
    """A change that makes the email column a keyed hash (chunked runs allow it; a vault needs it)."""

    def change(c: dict) -> None:
        c.setdefault("global_settings", {})["mask_secret_ref"] = TEST_MASK_SECRET_REF
        email = next(col for col in c["tables"][0]["columns"] if col["name"] == "email")
        email.clear()
        email.update(name="email", strategy="hash", namespace="em")
        if vault:
            email["vault"] = True

    return change


def _place(project: Path, kind: str, output: Path) -> list[str]:  # noqa: F811
    """Make the run write `kind`'s file at `output`; returns the extra arguments."""
    if kind in ("target", "chunked"):
        _edit(project, lambda c: c["targets"]["customers"].update(path=str(output)))
        if kind == "chunked":
            _edit(project, _keyed(vault=False))
        return ["--chunked"] if kind == "chunked" else []
    if kind == "quarantine":
        # One delivery folder: the target sits beside the quarantine file.
        def change(c: dict) -> None:
            c["targets"]["customers"]["path"] = str(output.parent / "masked.csv")
            c["quarantine"] = {"enabled": True, "output_path": str(output)}

        _edit(project, change)
        if output.is_symlink():
            # Both land in one folder, as the delivery-root rule asks.
            (output.parent / "masked.csv").symlink_to(
                Path(os.readlink(output)).parent / "masked.csv"
            )
        return []
    if kind == "integrity-implicit":
        # The report sits beside the first target under the config's name, so the target goes
        # next to the wanted report path.
        assert output.name == "customers.post-scan.json"

        def change(c: dict) -> None:
            c["targets"]["customers"]["path"] = str(output.parent / "masked.csv")
            c["post_scan"] = {"integrity": True}

        _edit(project, change)
        return []
    if kind == "vault":
        _edit(project, _keyed(vault=True))
    return [FLAGS[kind], str(output)]


def _name(kind: str, plain: str = "x.json") -> str:
    return "customers.post-scan.json" if kind == "integrity-implicit" else plain


def _layout(tmp_path: Path, relation: str, kind: str) -> tuple[Path, Path, Path]:
    """The root, the output and the folder the case builds in, for one relation."""
    folder = tmp_path / "d"
    folder.mkdir()
    name = _name(kind, "o.json")
    if relation == "equal":
        return folder / name, folder / name, folder
    if relation == "below":
        root = folder / "lib"
        return root, root / _name(kind), folder
    if relation == "ancestor":
        output = folder / name
        return output / "lib", output, folder
    real = folder / "real"
    real.mkdir()
    if relation == "alias-parent":
        (folder / "link").symlink_to(real, target_is_directory=True)
        return real, folder / "link" / _name(kind), folder
    if relation == "alias-root":
        (folder / "rootlink").symlink_to(real, target_is_directory=True)
        return folder / "rootlink", real / _name(kind), folder
    (folder / "sub").mkdir()
    alias = folder / "sub" / name  # the last part of the output is a link pointing into the root
    alias.symlink_to(real / _name(kind))
    return real, alias, folder


RELATIONS = ["equal", "below", "ancestor", "alias-parent", "alias-root", "alias-final"]


SHARED_FOLDER = ("integrity-implicit", "quarantine")


def _expected_labels(kind: str, relation: str) -> tuple[str, ...]:
    # The report and the quarantine file share their folder with the first target, so wherever
    # they are inside the root the target is too, and the inventory names the target first.
    if kind in SHARED_FOLDER and relation not in ("equal", "ancestor"):
        return (LABELS[kind], LABELS["target"])
    return (LABELS[kind],)


@pytest.mark.parametrize("relation", RELATIONS)
@pytest.mark.parametrize("kind", KINDS)
def test_an_output_that_overlaps_the_library_root_is_refused_before_any_write(
    project: Path,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    kind: str,
    relation: str,
) -> None:
    if relation.startswith("alias") and os.name == "nt":
        pytest.skip("needs symlinks")
    root, output, folder = _layout(tmp_path, relation, kind)
    monkeypatch.setenv("DECOY_LIBRARY", str(root))
    args = _place(project, kind, output)
    with mock.patch("decoy_engine.run_pipeline") as engine:
        result = _run(*args)
    assert result.exit_code == EXIT_USAGE, result.output
    assert COLLISION in result.output
    assert LIBRARY in result.output
    assert any(label in result.output for label in _expected_labels(kind, relation))
    engine.assert_not_called()
    existing = root.resolve()
    assert not existing.exists() or not any(existing.iterdir())
    if relation in ("equal", "below", "ancestor"):
        assert not os.path.lexists(output)
    assert not (project / DECOY_DIR).exists()
    assert not (project / "out").exists()
    assert sorted(p.name for p in folder.iterdir()) == sorted(
        {
            "equal": [],
            "below": [],
            "ancestor": [],
            "alias-parent": ["link", "real"],
            "alias-root": ["real", "rootlink"],
            "alias-final": ["real", "sub"],
        }[relation]
    )


@pytest.mark.parametrize("source", ["unset", "relative", "absolute"])
def test_each_root_source_is_held_for_a_target(
    project: Path,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    source: str,
) -> None:
    if source == "unset":
        root = project / DECOY_DIR
    elif source == "relative":
        monkeypatch.setenv("DECOY_LIBRARY", "mylib")
        root = project / "mylib"
    else:
        root = project.parent / "abs-lib"
        monkeypatch.setenv("DECOY_LIBRARY", str(root))
    _place(project, "target", root / "masked.csv")
    with mock.patch("decoy_engine.run_pipeline") as engine:
        result = _run()
    assert result.exit_code == EXIT_USAGE, result.output
    assert COLLISION in result.output and LIBRARY in result.output
    engine.assert_not_called()
    assert not root.exists()


def test_a_relative_library_env_cannot_take_the_result_file(
    project: Path,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DECOY_LIBRARY", "r.json")
    result = _run("--result", "r.json")
    assert result.exit_code == EXIT_USAGE, result.output
    assert COLLISION in result.output
    assert not (project / "r.json").exists()


@pytest.mark.parametrize(
    ("relation", "root_of"),
    [
        ("equal", lambda out, name: out / name / "PIPELINE"),
        ("above", lambda out, name: out),
        ("ancestor", lambda out, name: out / name / "LATEST" / "lib"),
    ],
)
def test_the_run_folder_files_are_held_off_the_library_root(
    project: Path,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    relation: str,
    root_of,
) -> None:
    root = root_of(project / "out", "customers")
    monkeypatch.setenv("DECOY_LIBRARY", str(root))
    with mock.patch("decoy_engine.run_pipeline") as engine:
        result = _run()
    assert result.exit_code == EXIT_USAGE, result.output
    assert COLLISION in result.output and LIBRARY in result.output
    assert "the run folder" in result.output or "targets.customers.path" in result.output
    engine.assert_not_called()
    assert not (project / "out").exists()


@pytest.mark.parametrize("how", ["flag", "off"])
@pytest.mark.parametrize("kind", KINDS)
def test_with_records_off_the_root_is_free_for_every_output(
    project: Path,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    kind: str,
    how: str,
) -> None:
    root = tmp_path / "d" / "lib"
    root.parent.mkdir()
    monkeypatch.setenv("DECOY_LIBRARY", str(root) if how == "flag" else "off")
    args = _place(project, kind, (root if how == "flag" else project / DECOY_DIR) / _name(kind))
    if how == "flag":
        args.append("--no-library")
    result = _run(*args)
    assert COLLISION not in result.output, result.output


# --- a root that cannot be resolved ---------------------------------------------------------


def _loop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "loop-a").symlink_to(tmp_path / "loop-b")
    (tmp_path / "loop-b").symlink_to(tmp_path / "loop-a")
    monkeypatch.setenv("DECOY_LIBRARY", str(tmp_path / "loop-a" / "lib"))


def _folders_named(top: Path, name: str) -> list[str]:
    return [d for _p, dirs, _f in os.walk(top) for d in dirs if d == name]


@SYMLINKS
@pytest.mark.parametrize("kind", KINDS)
def test_a_root_fault_delivers_the_outputs_and_stores_nothing(
    project: Path,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    kind: str,
) -> None:
    _loop(tmp_path, monkeypatch)
    safe = tmp_path / "safe"
    safe.mkdir()
    args = _place(project, kind, safe / _name(kind))
    result = _run("--json", *args)
    assert result.exit_code == EXIT_OK, result.output
    assert json.loads(result.stdout)["library"] == {
        "status": "failed",
        "code": "library_path_unsafe",
    }
    warnings = [ln for ln in result.stderr.splitlines() if "library_path_unsafe" in ln]
    assert len(warnings) == 1, result.stderr
    assert _folders_named(tmp_path, "library") == []
    assert not (project / DECOY_DIR).exists()


@SYMLINKS
@pytest.mark.parametrize("failure", ["success", "runtime"])
def test_a_root_fault_warns_exactly_once_and_keeps_the_exit_code(
    project: Path,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure: str,
) -> None:
    _loop(tmp_path, monkeypatch)
    if failure == "runtime":
        with mock.patch("decoy_engine.run_pipeline", side_effect=RuntimeError("boom")):
            result = _run("--quiet")
        assert result.exit_code == EXIT_RUNTIME, result.output
    else:
        result = _run("--quiet")
        assert result.exit_code == EXIT_OK, result.output
    assert len([ln for ln in result.stderr.splitlines() if "library_path_unsafe" in ln]) == 1
    assert _folders_named(tmp_path, "library") == []


@SYMLINKS
def test_a_root_fault_resolves_the_root_once_per_run(
    project: Path,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from decoy.cli import library as facade

    calls: list[int] = []
    real = facade.resolve_root

    def counted(**kwargs):
        calls.append(1)
        return real(**kwargs)

    with mock.patch.object(facade, "resolve_root", counted):
        assert _run().exit_code == EXIT_OK
    assert len(calls) == 1


def test_the_record_stores_never_resolve_a_root() -> None:
    """Rule 3: the run resolves the root once and hands it to the stores (MO-re-resolve)."""
    import ast

    from decoy.cli.library import _run_records

    source = Path(_run_records.__file__).read_text(encoding="utf-8")
    names = {n.id for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Name)}
    names |= {n.attr for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Attribute)}
    names |= {
        a.name
        for n in ast.walk(ast.parse(source))
        if isinstance(n, ast.ImportFrom)
        for a in n.names
    }
    assert "resolve_root" not in names
