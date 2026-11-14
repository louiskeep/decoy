"""One config loader on every command (DUP-FREEZE CL3: AT-CL3-1, -2, -6, -8, -9).

A config that is not UTF-8, empty or not a mapping gets the same code and text from `validate`,
`tokenize`, `detokenize`, `unmask`, `report`, `subset`, `preflight`, `compile-explain` and `run`,
never a codec message or a traceback.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy._config_file import ConfigFileError, load_config_mapping
from decoy.cli.exit_codes import EXIT_USAGE, exit_code_for
from decoy.cli.gate import gate_exit_code, run_config_gate, run_gate

runner = CliRunner()
_WIDE = {"COLUMNS": "10000"}

NOT_UTF8 = b"version: 2\nname: caf\xff\n"
NOT_UTF8_TEXT = "Pipeline YAML is not UTF-8 text."
EMPTY_TEXT = "Pipeline YAML is empty."
LIST_TEXT = "Pipeline YAML must be a YAML mapping (object), not list."

Argv = Callable[[str, str, Path], list[str]]

# Each builder takes (config path, csv path, tmp dir). The `report vault` file is any file: the
# command reads the config first.
COMMANDS: dict[str, Argv] = {
    "validate": lambda cfg, csv, d: ["validate", cfg],
    "validate config": lambda cfg, csv, d: ["validate", "config", cfg],
    "validate compile": lambda cfg, csv, d: ["validate", "compile", cfg],
    "validate preflight": lambda cfg, csv, d: ["validate", "preflight", cfg],
    "tokenize": lambda cfg, csv, d: ["tokenize", cfg, "--vault", str(d / "v.db")],
    "detokenize": lambda cfg, csv, d: ["detokenize", cfg, csv, "--vault", str(d / "v.db")],
    "unmask": lambda cfg, csv, d: ["unmask", cfg, csv],
    "report vault": lambda cfg, csv, d: ["report", "vault", csv, "--config", cfg],
    "report fidelity": lambda cfg, csv, d: ["report", "fidelity", csv, csv, "--config", cfg],
    "report integrity": lambda cfg, csv, d: [
        "report",
        "integrity",
        csv,
        "--source",
        csv,
        "--config",
        cfg,
    ],
    "subset": lambda cfg, csv, d: ["subset", cfg, "--dry-run"],
    "run": lambda cfg, csv, d: ["run", cfg],
}


@pytest.fixture
def csv(tmp_path: Path) -> str:
    path = tmp_path / "in.csv"
    path.write_text("a,b\n1,2\n", encoding="utf-8")
    return str(path)


def _config(tmp_path: Path, data: bytes) -> str:
    path = tmp_path / "pipeline.yaml"
    path.write_bytes(data)
    return str(path)


def _run(argv: list[str], *extra: str):
    return runner.invoke(app, [*argv, *extra], env=_WIDE, catch_exceptions=False)


def _everything(result) -> str:
    return (result.stdout or "") + (result.stderr or "")


@pytest.mark.parametrize("name", sorted(COMMANDS))
@pytest.mark.parametrize("extra", [(), ("--json",)], ids=["human", "json"])
def test_a_non_utf8_config_is_one_refusal(
    tmp_path: Path, csv: str, name: str, extra: tuple[str, ...]
) -> None:
    """AT-CL3-1."""
    cfg = _config(tmp_path, NOT_UTF8)

    result = _run(COMMANDS[name](cfg, csv, tmp_path), *extra)
    text = _everything(result)

    assert result.exit_code == EXIT_USAGE, text
    assert NOT_UTF8_TEXT in text, text
    if extra:  # the human gate report prints the text only; `--json` names the code
        assert "yaml.not_utf8" in text, text
    for codec_text in ("0xff", "codec", "UnicodeDecodeError", "can't decode", "Traceback"):
        assert codec_text not in text, text
    if extra:
        json.loads(result.stdout)  # the --json output stays one parseable document


@pytest.mark.parametrize("name", sorted(COMMANDS))
@pytest.mark.parametrize(
    ("data", "code", "message"),
    [
        (b"", "yaml.empty", EMPTY_TEXT),
        (b"- a\n- b\n", "yaml.not_mapping", LIST_TEXT),
    ],
    ids=["empty", "list"],
)
def test_an_empty_or_non_mapping_config_keeps_the_gate_text(
    tmp_path: Path, csv: str, name: str, data: bytes, code: str, message: str
) -> None:
    """AT-CL3-2."""
    cfg = _config(tmp_path, data)

    result = _run(COMMANDS[name](cfg, csv, tmp_path), "--json")
    text = _everything(result)

    assert result.exit_code == EXIT_USAGE, text
    assert code in text, text
    assert message in text, text


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (NOT_UTF8, "yaml.not_utf8"),
        (b"", "yaml.empty"),
        (b"- a\n", "yaml.not_mapping"),
        (b"a: [unclosed\n", "yaml.parse_error"),
    ],
)
def test_the_gate_exit_equals_the_loader_exit(tmp_path: Path, data: bytes, code: str) -> None:
    """AT-CL3-6."""
    path = Path(_config(tmp_path, data))
    with pytest.raises(ConfigFileError) as info:
        load_config_mapping(path)
    assert info.value.code == code

    for result in (run_gate(path), run_config_gate(path)):
        assert [f.code for f in result.findings] == [code]
        assert gate_exit_code(result, fail_on_warning=False) == exit_code_for(info.value) == 1


def test_run_on_a_non_utf8_config_writes_nothing(tmp_path: Path, csv: str) -> None:
    """AT-CL3-8: the refusal comes before any output file or evidence folder."""
    cfg = _config(tmp_path, NOT_UTF8)
    out = tmp_path / "out.csv"
    evidence = tmp_path / "evidence"
    before = {p.name for p in tmp_path.iterdir()}

    result = _run(["run", cfg, "--evidence-out", str(evidence), "--vault", str(tmp_path / "v.db")])

    assert result.exit_code == EXIT_USAGE, _everything(result)
    assert not out.exists() and not evidence.exists()
    assert {p.name for p in tmp_path.iterdir()} == before


def test_ci_check_reports_a_non_utf8_pipeline_with_its_own_rule(tmp_path: Path) -> None:
    """AT-CL3-9."""
    from decoy.ci.rule_codes import validation_codes
    from tests.ci_support import (
        MANIFEST_NAME,
        ci_check,
        ci_manifest,
        make_repo,
        parse_stdout,
        write,
        write_clean_pipeline,
    )

    repo = make_repo(tmp_path / "repo")
    write_clean_pipeline(repo)
    write(repo, MANIFEST_NAME, ci_manifest())
    write(repo, "pipeline.yaml", NOT_UTF8)

    proc = ci_check(repo, "--format", "json")

    assert proc.returncode == EXIT_USAGE, proc.stderr
    assert [f["rule_id"] for f in parse_stdout(proc)["findings"]] == ["validate.yaml.not_utf8"]
    assert "yaml.not_utf8" in validation_codes()


def test_an_unreadable_config_exits_3_with_a_json_object(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An `OSError` on the config read is the environment failing: exit 3, the type name only."""
    cfg = _config(tmp_path, b"version: 2\n")

    def _denied(self: Path) -> bytes:
        raise PermissionError(13, "SECRET-SYSTEM-TEXT", str(self))

    monkeypatch.setattr(Path, "read_bytes", _denied)

    result = _run(["validate", "compile", cfg], "--json")

    assert result.exit_code == 3, _everything(result)
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert payload["error"] == "could not read the config file: PermissionError."
    assert "SECRET-SYSTEM-TEXT" not in _everything(result)
