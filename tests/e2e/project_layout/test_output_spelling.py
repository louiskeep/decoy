"""Every writer of a gated output opens the spelling the collision gate keyed (P4).

`resolved_output_collisions` keys an absolute path with `Path(path).absolute()`, which keeps
`..`, and the kernel then follows symlinks. A writer that collapsed `..` as text first
(`os.path.abspath`) would open a different file than the one the gate compared. These cells
climb through a symlink with `..`, where the text and the kernel disagree.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_OK, EXIT_USAGE
from decoy.cli.io import resolved_output_collisions
from tests.e2e.project_layout.test_layout_gate import (
    COLLISION,
    _codes,
    _config,
    _project,
    _write,
    posix_only,
)
from tests.keyed_secret import TEST_MASK_SECRET, TEST_MASK_SECRET_ENV, TEST_MASK_SECRET_REF

runner = CliRunner()


def _vaulting(root: Path, target: str) -> Path:
    cfg_dict = _config(
        root, target, global_settings={"seed": 3, "mask_secret_ref": TEST_MASK_SECRET_REF}
    )
    cfg_dict["tables"][0]["columns"][0] = {
        "name": "email",
        "strategy": "hash",
        "namespace": "em",
        "vault": True,
    }
    return _write(root, "pipelines/orders/pipeline.yaml", cfg_dict)


def _climb(tmp_path: Path, name: str) -> tuple[str, Path, Path]:
    """`(spelling, kernel_path, text_collapsed_path)` for `<tmp>/link/../<name>`.

    `link` points at `real/deep`, so the kernel climbs to `real/<name>` while a text
    collapse of the same spelling names `<tmp>/<name>`.
    """
    (tmp_path / "real" / "deep").mkdir(parents=True)
    (tmp_path / "link").symlink_to(tmp_path / "real" / "deep", target_is_directory=True)
    spelling = f"{tmp_path}/link/../{name}"
    return spelling, Path(os.path.realpath(spelling)), Path(os.path.abspath(spelling))


@pytest.fixture(autouse=True)
def _secret(monkeypatch) -> None:
    monkeypatch.setenv(TEST_MASK_SECRET_ENV, TEST_MASK_SECRET)


@posix_only
@pytest.mark.parametrize("other", ["target", "--evidence-out"])
def test_a_vault_that_climbs_to_the_same_file_as_another_output_is_refused(
    tmp_path: Path, other: str
) -> None:
    spelling, kernel, _text = _climb(tmp_path, "vault.bin")
    root = _project(tmp_path)
    cfg = _vaulting(root, str(kernel) if other == "target" else "m.csv")
    args = ["run", str(cfg), "--json", "--vault", spelling]
    if other != "target":
        args += [other, str(kernel)]
    result = runner.invoke(app, args)
    assert result.exit_code == EXIT_USAGE, result.output
    assert COLLISION in _codes(result.output)
    assert not kernel.exists()
    assert not (tmp_path / "vault.bin").exists()


@posix_only
@pytest.mark.parametrize("other", ["target", "--evidence-out"])
def test_a_vault_that_climbs_elsewhere_is_not_refused_and_lands_where_the_kernel_says(
    tmp_path: Path, other: str
) -> None:
    spelling, kernel, text = _climb(tmp_path, "vault.bin")
    root = _project(tmp_path)
    cfg = _vaulting(root, str(text) if other == "target" else "m.csv")
    args = ["run", str(cfg), "--json", "--vault", spelling]
    if other != "target":
        args += [other, str(text)]
    result = runner.invoke(app, args)
    assert result.exit_code == EXIT_OK, result.output
    assert kernel.is_file()
    assert kernel.read_bytes() != text.read_bytes()
    # The other output kept its own file; the vault did not land on top of it (or it on the vault).
    expected = b"email" if other == "target" else b'"run_id"'
    assert expected in text.read_bytes()


@posix_only
@pytest.mark.parametrize("kind", ["target", "--evidence-out", "--vault"])
def test_every_writer_opens_the_spelling_the_gate_keyed(tmp_path: Path, kind: str) -> None:
    """Class guard: a spelling that climbs through a symlink lands where the kernel puts it."""
    name = {"target": "out.csv", "--evidence-out": "ev.json", "--vault": "vault.bin"}[kind]
    spelling, kernel, text = _climb(tmp_path, name)
    root = _project(tmp_path)
    cfg = _vaulting(root, spelling if kind == "target" else "m.csv")
    args = ["run", str(cfg), "--json"]
    # Each kind always has a vault so the run keeps a vault; only the one under test climbs.
    side = {"--evidence-out": tmp_path / "plain-ev.json", "--vault": tmp_path / "plain-vault.bin"}
    for flag, plain in side.items():
        args += [flag, spelling if flag == kind else str(plain)]
    result = runner.invoke(app, args)
    assert result.exit_code == EXIT_OK, result.output
    assert kernel.is_file()
    assert not text.exists()


@posix_only
def test_the_vault_temp_file_is_made_in_the_folder_the_kernel_resolves(
    tmp_path: Path, monkeypatch
) -> None:
    """`mkstemp` collapses `..` in its `dir` as text, so it must be handed the resolved folder:
    else the temp file lands in another folder (another filesystem fails the rename)."""
    import tempfile

    spelling, kernel, _text = _climb(tmp_path, "vault.bin")
    seen: list[str] = []
    real_mkstemp = tempfile.mkstemp

    def recording(*args, **kwargs):
        if str(kwargs.get("prefix", "")).startswith(".vault.bin."):
            seen.append(os.fspath(kwargs["dir"]))
        return real_mkstemp(*args, **kwargs)

    monkeypatch.setattr(tempfile, "mkstemp", recording)
    root = _project(tmp_path)
    cfg = _vaulting(root, "m.csv")
    result = runner.invoke(app, ["run", str(cfg), "--json", "--vault", spelling])
    assert result.exit_code == EXIT_OK, result.output
    assert seen == [os.path.realpath(kernel.parent)]
    assert sorted(p.name for p in kernel.parent.iterdir()) == ["deep", "vault.bin"]
    assert not list(tmp_path.glob(".vault.bin.*"))


# --- characterization -----------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["/tmp/bad\ud800.bin", "/tmp/nul\x00.bin"])
def test_characterization_the_destination_key_never_raises_on_unencodable_paths(raw: str) -> None:
    """Passes today (`UnicodeEncodeError` is a `ValueError`, which the key already catches)."""
    typed = (("--vault", Path(raw)), ("--evidence-out", Path(raw)))
    assert resolved_output_collisions({}, None, typed) in (None, ("--vault", "--evidence-out"))
    assert json.dumps(raw)  # the cell's input is a plain str, not bytes
