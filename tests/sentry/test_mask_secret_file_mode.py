"""A `file:` mask secret is admitted only when it is owner-only, and it is read once, checked.

Engine 0.17.0's `file:` provider opens the path with no permission check, so a world-readable
secret used to mask and write output. Every CLI surface that admits the secret (`run`, plain and
`--chunked`, `tokenize`, `unmask`, `report vault`, `decoy.mask()`) now opens the file itself,
checks the mode on the OPEN descriptor (group or other bits, a directory, or any non-regular file
is refused with the constant `secret_file_permissions_unsafe` text, exit 1, no output), and hands
the engine that same descriptor as `file:/dev/fd/N`.

The swap tests replace the path with a different, valid, owner-only secret right after the check.
If the engine read the path again (check then use), the output, the vault key or the reversal
would follow the new secret; they must follow the checked one. Each surface has its own swap
test so dropping the checked provider on any one of them fails here.

POSIX only: the mode check is skipped on Windows, where these bits do not describe access.
"""

from __future__ import annotations

import ast
import json
import os
from collections.abc import Mapping
from pathlib import Path

import pandas as pd
import pytest
import yaml
from tests.csv_sources import csv_source
from tests.sentry.io_policy._calls import sites
from typer.testing import CliRunner

from decoy import _mask_secret
from decoy.__main__ import app
from decoy._mask_secret_guidance import SECRET_REMEDIES
from decoy.cli.exit_codes import EXIT_USAGE

pytest.importorskip("cryptography")
pytestmark = pytest.mark.skipif(os.name == "nt", reason="the mode check is POSIX only")

runner = CliRunner()

UNSAFE_TEXT = SECRET_REMEDIES["secret_file_permissions_unsafe"]
SECRET = b"decoy-test-only-throwaway-key-32".hex()
OTHER_SECRET = b"other-test-only-throwaway-key-32".hex()
SOURCE = ["alice@example.com", "bob@example.com", "carol@example.com"]
UNSAFE_MODES = (0o644, 0o640, 0o604, 0o660)


def _key(path: Path, secret: str = SECRET, mode: int = 0o600) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(secret, encoding="utf-8")
    path.chmod(mode)
    return path


def _pipeline(root: Path, ref: str, *, strategy: str = "hash", vault: bool = True) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    src = root / "a.csv"
    pd.DataFrame({"email": SOURCE}).to_csv(src, index=False)
    column: dict = {"name": "email", "strategy": strategy, "namespace": "em"}
    if strategy == "hash" and vault:
        column["vault"] = True
    cfg = {
        "version": 2,
        "global_settings": {"seed": 3, "mask_secret_ref": ref},
        "sources": {"a": csv_source(src)},
        "tables": [{"name": "a", "columns": [column]}],
        "targets": {"a": {"type": "file", "format": "csv", "path": str(root / "out.csv")}},
    }
    path = root / "pipeline.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _masked_with_vault(root: Path) -> tuple[Path, Path]:
    """A masked file and its vault, written under SECRET through an owner-only key file."""
    key = _key(root / "writer.key")
    cfg = _pipeline(root, f"file:{key}")
    vault = root / "vault.bin"
    result = runner.invoke(app, ["run", str(cfg), "--vault", str(vault)])
    assert result.exit_code == 0, result.output
    return root / "out.csv", vault


def _argv(surface: str, root: Path, ref: str, written: tuple[Path, Path] | None) -> list[str]:
    if surface == "run":
        return ["run", str(_pipeline(root, ref)), "--vault", str(root / "fresh.bin")]
    if surface == "run_chunked":
        return ["run", str(_pipeline(root, ref, vault=False)), "--chunked"]
    if surface == "tokenize":
        cfg = _pipeline(root, ref, strategy="tokenize")
        return ["tokenize", str(cfg), "--vault", str(root / "tokens.db")]
    assert written is not None
    masked, vault = written
    cfg = _pipeline(root, ref)
    if surface == "unmask":
        out = root / "unmasked.csv"
        return ["unmask", str(cfg), str(masked), "--vault", str(vault), "--output", str(out)]
    if surface == "report_vault":
        return ["report", "vault", str(vault), "--config", str(cfg)]
    raise AssertionError(f"no argv for surface {surface!r}")


# Each place that admits a `file:` secret (a call to `admitted_key_provider`, keyed
# `file::function::ordinal` and derived from the AST below) to the surface ids that exercise it
# through the CLI, or the test functions in this module that exercise it through `decoy.mask()`.
ADMISSION_SITES: dict[str, tuple[str, ...]] = {
    "cli/run/_prepare.py::prepare::1": ("run", "run_chunked"),
    "cli/tokenize.py::tokenize::1": ("tokenize",),
    "cli/unmask.py::unmask::1": ("unmask",),
    "cli/report.py::_vault::1": ("report_vault",),
    "api.py::mask::1": (
        "test_api_mask_refuses_an_unsafe_file",
        "test_api_mask_reads_the_checked_descriptor",
    ),
}
_SRC = Path(__file__).resolve().parents[2] / "src" / "decoy"
_ADMITTER = "decoy._mask_secret.admitted_key_provider"


def admission_sites(files: Mapping[str, str]) -> list[str]:
    """Every `file::function::ordinal` that calls the admitting context manager."""
    found: list[str] = []
    for rel in sorted(files):
        seen: dict[str, int] = {}
        for site in sites(ast.parse(files[rel])):
            if isinstance(site.node, ast.Call) and site.name == _ADMITTER:
                n = seen[site.scope] = seen.get(site.scope, 0) + 1
                found.append(f"{rel}::{site.scope}::{n}")
    return found


def _is_test_name(ident: str) -> bool:
    return ident.startswith("test_")


def admission_findings(
    found: list[str], mapping: Mapping[str, tuple[str, ...]], module_source: str
) -> list[str]:
    """Derived sites against the mapping, and every mapped id against what handles it."""
    tree = ast.parse(module_source)
    tests = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    argv = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_argv")
    handled = {
        c.value
        for cmp in ast.walk(argv)
        if isinstance(cmp, ast.Compare)
        for c in cmp.comparators
        if isinstance(c, ast.Constant) and isinstance(c.value, str)
    }
    out = [f"admission site with no surface test: {k}" for k in sorted(set(found) - mapping.keys())]
    out += [f"mapping key with no live site: {k}" for k in sorted(mapping.keys() - set(found))]
    for key, ids in mapping.items():
        for ident in ids:
            if _is_test_name(ident) and ident not in tests:
                out.append(f"{key}: no test function {ident}")
            elif not _is_test_name(ident) and ident not in handled:
                out.append(f"{key}: surface {ident} is not handled by _argv")
    return out


_CLI_SURFACES = tuple(
    dict.fromkeys(i for ids in ADMISSION_SITES.values() for i in ids if not _is_test_name(i))
)
_NEEDS_VAULT = {"unmask", "report_vault"}


def _no_output(root: Path) -> None:
    for name in ("out.csv", "fresh.bin", "tokens.db", "unmasked.csv"):
        assert not (root / name).exists(), name


def _assert_refused(result, root: Path) -> None:
    assert result.exit_code == EXIT_USAGE, result.output
    assert " ".join(UNSAFE_TEXT.split()) in " ".join(result.output.split())
    assert "Traceback" not in result.output
    _no_output(root)


@pytest.mark.parametrize("scheme", ["file", "FILE"])  # the engine reads the scheme in any case
@pytest.mark.parametrize("mode", UNSAFE_MODES, ids=oct)
@pytest.mark.parametrize("surface", _CLI_SURFACES)
def test_unsafe_mode_is_refused_with_no_output(
    tmp_path: Path, surface: str, mode: int, scheme: str
) -> None:
    written = _masked_with_vault(tmp_path / "w") if surface in _NEEDS_VAULT else None
    key = _key(tmp_path / "k" / "secret.key", mode=mode)
    root = tmp_path / "r"
    argv = _argv(surface, root, f"{scheme}:{key}", written)
    _assert_refused(runner.invoke(app, argv), root)
    result = runner.invoke(app, [*argv, "--json"])
    assert result.exit_code == EXIT_USAGE
    assert json.loads(result.stdout)["error"] == UNSAFE_TEXT
    _no_output(root)


@pytest.mark.parametrize("surface", _CLI_SURFACES)
def test_symlink_to_an_unsafe_file_is_refused(tmp_path: Path, surface: str) -> None:
    written = _masked_with_vault(tmp_path / "w") if surface in _NEEDS_VAULT else None
    target = _key(tmp_path / "k" / "target.key", mode=0o644)
    link = tmp_path / "k" / "link.key"
    link.symlink_to(target)
    root = tmp_path / "r"
    _assert_refused(runner.invoke(app, _argv(surface, root, f"file:{link}", written)), root)


@pytest.mark.parametrize("surface", _CLI_SURFACES)
def test_a_directory_is_refused_with_the_owner_only_text(tmp_path: Path, surface: str) -> None:
    written = _masked_with_vault(tmp_path / "w") if surface in _NEEDS_VAULT else None
    directory = tmp_path / "k" / "dir.key"
    directory.mkdir(parents=True)
    directory.chmod(0o700)
    root = tmp_path / "r"
    _assert_refused(runner.invoke(app, _argv(surface, root, f"file:{directory}", written)), root)


@pytest.mark.parametrize("surface", _CLI_SURFACES)
def test_owner_only_file_is_admitted(tmp_path: Path, surface: str) -> None:
    """Positive control: 0600 (and a symlink to a 0600 file) masks, reverses and opens."""
    written = _masked_with_vault(tmp_path / "w") if surface in _NEEDS_VAULT else None
    target = _key(tmp_path / "k" / "secret.key")
    link = tmp_path / "k" / "link.key"
    link.symlink_to(target)
    for i, ref in enumerate((f"file:{target}", f"file:{link}")):
        root = tmp_path / f"r{i}"
        result = runner.invoke(app, _argv(surface, root, ref, written))
        assert result.exit_code == 0, result.output
        if surface == "unmask":
            assert pd.read_csv(root / "unmasked.csv")["email"].tolist() == SOURCE


def _swap_after_check(monkeypatch: pytest.MonkeyPatch, key: Path, replacement: Path) -> list[int]:
    """Replace the key path with another inode right after the CLI's first check passes."""
    real = _mask_secret._open_checked
    swaps: list[int] = []

    def _checked_then_swapped(locator: str) -> int:
        fd = real(locator)
        if not swaps and os.path.samefile(locator, key):
            os.replace(replacement, key)
            swaps.append(fd)
        return fd

    monkeypatch.setattr(_mask_secret, "_open_checked", _checked_then_swapped)
    return swaps


def _output_bytes(surface: str, root: Path) -> bytes:
    if surface in ("run", "run_chunked", "tokenize"):
        return (root / "out.csv").read_bytes()
    if surface == "unmask":
        return (root / "unmasked.csv").read_bytes()
    return b""


@pytest.mark.parametrize("surface", _CLI_SURFACES)
def test_swapping_the_path_after_the_check_changes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, surface: str
) -> None:
    """The engine reads the checked descriptor: a swap changes neither output nor vault key."""
    written = _masked_with_vault(tmp_path / "w") if surface in _NEEDS_VAULT else None
    control_key = _key(tmp_path / "control" / "secret.key")
    control_root = tmp_path / "control"
    control = runner.invoke(app, _argv(surface, control_root, f"file:{control_key}", written))
    assert control.exit_code == 0, control.output

    key = _key(tmp_path / "k" / "secret.key")
    replacement = _key(tmp_path / "k" / "other.key", secret=OTHER_SECRET)
    swaps = _swap_after_check(monkeypatch, key, replacement)
    root = tmp_path / "r"
    result = runner.invoke(app, _argv(surface, root, f"file:{key}", written))
    assert swaps, "the CLI never checked the secret file"
    assert key.read_text(encoding="utf-8") == OTHER_SECRET  # the swap really happened
    assert result.exit_code == 0, result.output
    assert _output_bytes(surface, root) == _output_bytes(surface, control_root)
    if surface == "run":
        # The vault opens under the checked secret, not the swapped-in one.
        good = _pipeline(tmp_path / "check_good", f"file:{control_key}")
        opened = runner.invoke(
            app, ["report", "vault", str(root / "fresh.bin"), "--config", str(good)]
        )
        assert opened.exit_code == 0, opened.output
        other = _key(tmp_path / "check_bad" / "other.key", secret=OTHER_SECRET)
        bad = _pipeline(tmp_path / "check_bad", f"file:{other}")
        refused = runner.invoke(
            app, ["report", "vault", str(root / "fresh.bin"), "--config", str(bad)]
        )
        assert refused.exit_code != 0
    if surface == "report_vault":
        assert "vault_key_mismatch" not in result.output


# --- decoy.mask() -------------------------------------------------------------------------


def _api_config(ref: str) -> dict:
    return {
        "version": 2,
        "global_settings": {"seed": 3, "mask_secret_ref": ref},
        "tables": [
            {"name": "a", "columns": [{"name": "email", "strategy": "hash", "namespace": "em"}]}
        ],
    }


@pytest.mark.parametrize("mode", UNSAFE_MODES, ids=oct)
def test_api_mask_refuses_an_unsafe_file(tmp_path: Path, mode: int) -> None:
    import decoy
    from decoy.api import MaskSecretConfigError

    key = _key(tmp_path / "secret.key", mode=mode)
    out = tmp_path / "out.csv"
    with pytest.raises(MaskSecretConfigError) as caught:
        decoy.mask(pd.DataFrame({"email": SOURCE}), _api_config(f"file:{key}"), out=str(out))
    assert str(caught.value) == UNSAFE_TEXT
    assert not out.exists()


def test_api_mask_refuses_a_symlink_to_an_unsafe_file(tmp_path: Path) -> None:
    import decoy
    from decoy.api import MaskSecretConfigError

    target = _key(tmp_path / "target.key", mode=0o644)
    link = tmp_path / "link.key"
    link.symlink_to(target)
    out = tmp_path / "out.csv"
    with pytest.raises(MaskSecretConfigError, match="secret_file_permissions_unsafe"):
        decoy.mask(pd.DataFrame({"email": SOURCE}), _api_config(f"file:{link}"), out=str(out))
    assert not out.exists()


def test_api_mask_reads_the_checked_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import decoy

    control_key = _key(tmp_path / "control.key")
    control = decoy.mask(
        pd.DataFrame({"email": SOURCE}),
        _api_config(f"file:{control_key}"),
        out=str(tmp_path / "c.csv"),
    )
    key = _key(tmp_path / "secret.key")
    replacement = _key(tmp_path / "other.key", secret=OTHER_SECRET)
    swaps = _swap_after_check(monkeypatch, key, replacement)
    swapped = decoy.mask(
        pd.DataFrame({"email": SOURCE}), _api_config(f"file:{key}"), out=str(tmp_path / "s.csv")
    )
    assert swaps, "decoy.mask() never checked the secret file"
    assert key.read_text(encoding="utf-8") == OTHER_SECRET
    assert (tmp_path / "s.csv").read_bytes() == (tmp_path / "c.csv").read_bytes()
    assert swapped is not None and control is not None


# --- the admission sites are derived from the AST (AT-S1) ---------------------------------


def _live_sources() -> dict[str, str]:
    return {
        p.relative_to(_SRC).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(_SRC.rglob("*.py"))
    }


def test_the_five_admission_sites_are_found_and_mapped() -> None:
    found = admission_sites(_live_sources())
    assert len(found) == 5
    assert admission_findings(found, ADMISSION_SITES, Path(__file__).read_text("utf-8")) == []


def test_a_sixth_admission_call_with_no_surface_test_fails() -> None:
    files = {**_live_sources(), "cli/new.py": _SEEDED_ADMIT}
    assert "cli/new.py::go::1" in admission_sites(files)
    findings = admission_findings(
        admission_sites(files), ADMISSION_SITES, Path(__file__).read_text("utf-8")
    )
    assert findings == ["admission site with no surface test: cli/new.py::go::1"]


def test_a_second_call_in_an_already_mapped_function_fails() -> None:
    files = _live_sources()
    old = "with _mask_secret.admitted_key_provider(raw) as key_provider:"
    assert old in files["cli/unmask.py"]
    files["cli/unmask.py"] = files["cli/unmask.py"].replace(
        old,
        "with _mask_secret.admitted_key_provider(raw), "
        "_mask_secret.admitted_key_provider(raw) as key_provider:",
        1,
    )
    found = admission_sites(files)
    assert "cli/unmask.py::unmask::2" in found
    findings = admission_findings(found, ADMISSION_SITES, Path(__file__).read_text("utf-8"))
    assert findings == ["admission site with no surface test: cli/unmask.py::unmask::2"]


def test_a_mapped_id_that_is_not_handled_or_a_missing_test_fails() -> None:
    source = Path(__file__).read_text("utf-8")
    found = admission_sites(_live_sources())
    bad = {**ADMISSION_SITES, "cli/unmask.py::unmask::1": ("unmask", "unmask_twice")}
    assert admission_findings(found, bad, source) == [
        "cli/unmask.py::unmask::1: surface unmask_twice is not handled by _argv"
    ]
    bad = {**ADMISSION_SITES, "api.py::mask::1": ("test_api_mask_is_gone",)}
    assert admission_findings(found, bad, source) == [
        "api.py::mask::1: no test function test_api_mask_is_gone"
    ]


def test_a_mapping_key_with_no_live_site_fails() -> None:
    found = admission_sites(_live_sources())
    stale = {**ADMISSION_SITES, "cli/gone.py::f::1": ("run",)}
    assert admission_findings(found, stale, Path(__file__).read_text("utf-8")) == [
        "mapping key with no live site: cli/gone.py::f::1"
    ]


_SEEDED_ADMIT = (
    "from decoy import _mask_secret\n"
    "def go(raw):\n    with _mask_secret.admitted_key_provider(raw):\n        pass\n"
)


# --- non-mapping YAML is guarded before the file check -------------------------------------


# Both surfaces now admit the same way, so both get the engine's coded admission refusal
# (exit 1, constant text). On b9fd22db `report vault` already did; `unmask` reached its engine
# entry first and printed `unmask failed: AttributeError` (exit 3). The guard keeps the CLI's
# own file check from parsing the list (last round's crash in `_file_ref_locator`).
_LIST_SETTINGS_EXIT = {"unmask": EXIT_USAGE, "report_vault": EXIT_USAGE}


@pytest.mark.parametrize("surface", ["unmask", "report_vault"])
def test_list_valued_global_settings_keeps_its_outcome(tmp_path: Path, surface: str) -> None:
    """A list `global_settings` (unvalidated YAML) is not parsed by the file check."""
    masked, vault = _masked_with_vault(tmp_path / "w")
    cfg = _pipeline(tmp_path / "r", "env:UNUSED")
    data = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    data["global_settings"] = ["seed", 3]
    cfg.write_text(yaml.safe_dump(data), encoding="utf-8")
    argv = (
        ["unmask", str(cfg), str(masked), "--vault", str(vault)]
        if surface == "unmask"
        else ["report", "vault", str(vault), "--config", str(cfg)]
    )
    checked: list[str] = []
    real = _mask_secret._open_checked
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(_mask_secret, "_open_checked", lambda loc: checked.append(loc) or real(loc))
        result = runner.invoke(app, argv)
    assert result.exit_code == _LIST_SETTINGS_EXIT[surface], result.output
    assert "secret_provider_unavailable" in result.output
    assert "Traceback" not in result.output and "AttributeError" not in result.output
    assert checked == []
