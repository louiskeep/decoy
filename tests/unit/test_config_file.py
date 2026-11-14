"""The one config loader: every read, decode, parse and shape failure maps to one code.

AT-CL3-3 (no exception context, no file bytes) and AT-CL3-5 (one open of the path) live here;
the per-command behaviour is in `tests/e2e/test_config_loader_commands.py`.
"""

from __future__ import annotations

import builtins
import pathlib
from pathlib import Path

import pytest

from decoy._config_file import (
    ConfigFileError,
    load_config_mapping,
    parse_config_mapping,
    read_config_text,
)

SECRET = "SECRET-LINE-VALUE-9f3a"


def _write(tmp_path: Path, data: bytes) -> Path:
    path = tmp_path / "pipeline.yaml"
    path.write_bytes(data)
    return path


def _refusal(tmp_path: Path, data: bytes) -> ConfigFileError:
    path = _write(tmp_path, data)
    with pytest.raises(ConfigFileError) as info:
        load_config_mapping(path)
    return info.value


@pytest.mark.parametrize(
    ("data", "code", "message"),
    [
        (b"a: \xff\n", "yaml.not_utf8", "Pipeline YAML is not UTF-8 text."),
        (b"", "yaml.empty", "Pipeline YAML is empty."),
        (b"# only a comment\n", "yaml.empty", "Pipeline YAML is empty."),
        (
            b"- a\n- b\n",
            "yaml.not_mapping",
            "Pipeline YAML must be a YAML mapping (object), not list.",
        ),
        (
            b"just text\n",
            "yaml.not_mapping",
            "Pipeline YAML must be a YAML mapping (object), not str.",
        ),
    ],
)
def test_each_failure_has_one_code_and_text(
    tmp_path: Path, data: bytes, code: str, message: str
) -> None:
    exc = _refusal(tmp_path, data)

    assert (exc.code, exc.message) == (code, message)
    assert str(exc) == message


def test_a_parse_failure_names_a_coordinate_never_the_line(tmp_path: Path) -> None:
    exc = _refusal(tmp_path, f"version: 2\nkey: [{SECRET}\n".encode())

    assert exc.code == "yaml.parse_error"
    assert SECRET not in exc.message


def test_a_mapping_loads_and_a_bom_is_stripped(tmp_path: Path) -> None:
    path = _write(tmp_path, b"\xef\xbb\xbfversion: 2\n")

    assert read_config_text(path) == "version: 2\n"
    assert load_config_mapping(path) == {"version": 2}


def test_a_read_failure_is_the_os_error_unchanged(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_config_mapping(tmp_path / "missing.yaml")


def test_parse_config_mapping_takes_text() -> None:
    assert parse_config_mapping("a: 1\n") == {"a": 1}
    with pytest.raises(ConfigFileError) as info:
        parse_config_mapping("")
    assert info.value.code == "yaml.empty"


# AT-CL3-3
@pytest.mark.parametrize(
    "data",
    [
        b"a: \xff" + SECRET.encode() + b"\n",
        f"key: [{SECRET}\n".encode(),
        b"",
        b"- a\n",
    ],
)
def test_a_loader_error_has_no_context_and_no_file_bytes(tmp_path: Path, data: bytes) -> None:
    exc = _refusal(tmp_path, data)

    assert exc.__cause__ is None
    assert exc.__context__ is None
    assert SECRET not in str(exc) + repr(exc) + exc.message
    assert "0xff" not in str(exc) + repr(exc)
    assert "codec" not in str(exc) + repr(exc)


# AT-CL3-5
def test_the_loader_opens_the_path_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = _write(tmp_path, b"version: 2\n")
    opened: list[str] = []
    real_builtin, real_path_open = builtins.open, pathlib.Path.open

    def counting_open(file, *args, **kwargs):
        opened.append(str(file))
        return real_builtin(file, *args, **kwargs)

    def counting_path_open(self, *args, **kwargs):
        opened.append(str(self))
        return real_path_open(self, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", counting_open)
    monkeypatch.setattr(pathlib.Path, "open", counting_path_open)

    assert load_config_mapping(path) == {"version": 2}
    assert [p for p in opened if p == str(path)] == [str(path)]
