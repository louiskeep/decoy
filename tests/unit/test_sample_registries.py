"""One owner each for target formats, user-chosen file names and the project library root
(SAMPLE SC1 review fixes): SAMPLE and result building consume them, never copy them."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from decoy.cli.io import (
    TARGET_SUFFIX,
    TargetFormatError,
    declared_format,
    is_portable_component,
    is_target_format,
    resolve_target_format,
    sample_target_format,
)
from decoy.cli.library import resolve_project_root
from decoy.cli.run import _sample

RUN = Path(__file__).resolve().parents[2] / "src" / "decoy" / "cli" / "run"


def test_every_supported_format_has_a_sample_suffix_and_a_sample_target() -> None:
    for fmt, suffix in TARGET_SUFFIX.items():
        assert is_target_format(fmt) and suffix.startswith(".")
        entry = {"type": "file", "format": fmt, "path": f"x{suffix}"}
        assert declared_format(entry) == fmt
        assert sample_target_format("t", entry) == fmt
        if fmt != "fixed_width":
            assert resolve_target_format("t", entry) == fmt
        spec = _sample.sample_config({"targets": {"t": {**entry, "layout": {"c": 1}}}})
        assert spec["targets"]["t"]["path"] == f"t{suffix}"


def test_sample_and_result_hold_no_format_registry_of_their_own() -> None:
    for name in ("_sample.py", "_result.py"):
        text = (RUN / name).read_text(encoding="utf-8")
        assert not re.search(r"""["']fixed_width["']\s*[,:]\s*["'.]""", text), name
        assert not re.search(r"\b_(FORMATS|SUFFIX)\b", text), name


def test_an_unsupported_file_format_is_refused_as_the_gate_refuses_it() -> None:
    entry = {"type": "file", "format": "xml", "path": "x.xml"}
    with pytest.raises(TargetFormatError) as caught:
        sample_target_format("t", entry)
    assert caught.value.code == "target_format_unknown"
    with pytest.raises(TargetFormatError):
        _sample.sample_config({"targets": {"t": entry}})
    assert sample_target_format("t", {"type": "s3", "format": "xml"}) == "parquet"
    assert declared_format({"format": "xml"}) is None and declared_format(None) is None


@pytest.mark.parametrize("name", ["a b", ".hidden", "naïve", "表", "ok.csv"])
def test_portable_components_pass(name: str) -> None:
    assert is_portable_component(name)


@pytest.mark.parametrize(
    "name", ["", ".", "..", "a/b", "a\\b", "a\x00b", "C:x", "CON", "nul.txt", "COM1", 3, None]
)
def test_non_portable_components_fail(name: object) -> None:
    assert not is_portable_component(name)


def test_the_project_root_ignores_decoy_library(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DECOY_LIBRARY", str(tmp_path / "elsewhere"))
    got = resolve_project_root(tmp_path / "proj")
    assert got.path == tmp_path / "proj" / ".decoy" and got.source == "project"
