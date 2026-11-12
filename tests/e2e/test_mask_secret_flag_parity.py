"""`--mask-secret` on every command that needs the mask secret, and parity with the YAML ref.

`decoy run`, `decoy unmask` and `decoy report vault` each take the secret the same two ways,
`--mask-secret REF` or `global_settings.mask_secret_ref`, in exactly one place. A vault and an
fpe column written under one way open under the other. With neither, each command refuses
with its own constant remedy before writing anything.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy import _mask_secret_guidance as guidance
from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_USAGE
from tests.csv_sources import csv_source
from tests.keyed_secret import TEST_MASK_SECRET, TEST_MASK_SECRET_REF

pytest.importorskip("cryptography")
pytestmark = pytest.mark.usefixtures("mask_secret")

runner = CliRunner()

_ROWS = 20
_EMAILS = [f"user{i}@example.com" for i in range(_ROWS)]
_SSNS = [f"{100000000 + i}" for i in range(_ROWS)]


def _pipeline(tmp_path: Path, *, ref: str | None) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    src = tmp_path / "in.csv"
    pd.DataFrame({"email": _EMAILS, "ssn": _SSNS}).to_csv(src, index=False)
    settings: dict = {"seed": 42}
    if ref is not None:
        settings["mask_secret_ref"] = ref
    cfg = {
        "version": 2,
        "global_settings": settings,
        "sources": {"accounts": csv_source(src)},
        "tables": [
            {
                "name": "accounts",
                "columns": [
                    {"name": "email", "strategy": "hash", "namespace": "em", "vault": True},
                    {
                        "name": "ssn",
                        "strategy": "fpe",
                        "namespace": "ssn",
                        "provider_config": {"charset": "digits"},
                    },
                ],
            }
        ],
        "targets": {
            "accounts": {"type": "file", "format": "csv", "path": str(tmp_path / "out.csv")}
        },
    }
    path = tmp_path / "pipeline.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _flag(how: str) -> list[str]:
    return ["--mask-secret", TEST_MASK_SECRET_REF] if how == "flag" else []


def _masked_run(tmp_path: Path, how: str) -> tuple[Path, Path]:
    cfg = _pipeline(tmp_path, ref=TEST_MASK_SECRET_REF if how == "yaml" else None)
    vault = tmp_path / "vault.bin"
    result = runner.invoke(app, ["run", str(cfg), "--vault", str(vault), *_flag(how)])
    assert result.exit_code == 0, result.output
    return cfg, vault


@pytest.mark.parametrize("write", ["yaml", "flag"])
@pytest.mark.parametrize("read", ["yaml", "flag"])
def test_vault_and_fpe_open_under_either_way_of_naming_the_secret(
    tmp_path: Path, write: str, read: str
) -> None:
    """T-4a.2 / T-4a.4: a run under one way opens under the other, on unmask and report vault."""
    _, vault = _masked_run(tmp_path / "w", write)
    reader = _pipeline(tmp_path / "r", ref=TEST_MASK_SECRET_REF if read == "yaml" else None)
    masked = tmp_path / "w" / "out.csv"

    report = runner.invoke(
        app, ["report", "vault", str(vault), "--config", str(reader), *_flag(read), "--json"]
    )
    assert report.exit_code == 0, report.output
    assert json.loads(report.stdout)["entries"] == _ROWS

    out = tmp_path / "recovered.csv"
    unmask = runner.invoke(
        app,
        ["unmask", str(reader), str(masked), "--vault", str(vault), "-o", str(out), *_flag(read)],
    )
    assert unmask.exit_code == 0, unmask.output
    recovered = pd.read_csv(out, dtype=str)
    assert recovered["email"].tolist() == _EMAILS
    assert recovered["ssn"].tolist() == _SSNS


def test_unmask_flag_and_yaml_ref_give_identical_results(tmp_path: Path) -> None:
    """T-4a.4: the same bytes and the same per-column report either way."""
    cfg, vault = _masked_run(tmp_path, "yaml")
    bare = _pipeline(tmp_path / "bare", ref=None)
    masked = tmp_path / "out.csv"
    outputs = []
    for config, extra, name in ((cfg, [], "a.csv"), (bare, _flag("flag"), "b.csv")):
        result = runner.invoke(
            app,
            [
                *["unmask", str(config), str(masked), "--vault", str(vault)],
                *["-o", str(tmp_path / name), *extra, "--json"],
            ],
        )
        assert result.exit_code == 0, result.output
        outputs.append(json.loads(result.stdout)["columns"])
    assert outputs[0] == outputs[1]
    assert (tmp_path / "a.csv").read_bytes() == (tmp_path / "b.csv").read_bytes()


def _commands(cfg: Path, vault: Path, masked: Path, fresh_vault: Path) -> dict[str, list[str]]:
    return {
        "run": ["run", str(cfg), "--vault", str(fresh_vault)],
        "unmask": ["unmask", str(cfg), str(masked), "--vault", str(vault)],
        "report_vault": ["report", "vault", str(vault), "--config", str(cfg)],
    }


@pytest.mark.parametrize("command", ["run", "unmask", "report_vault"])
def test_flag_and_yaml_ref_both_set_is_a_usage_error(tmp_path: Path, command: str) -> None:
    cfg, vault = _masked_run(tmp_path, "yaml")
    masked = tmp_path / "out.csv"
    before = masked.read_bytes()
    fresh = tmp_path / "fresh.bin"
    argv = _commands(cfg, vault, masked, fresh)[command]
    result = runner.invoke(app, [*argv, "--mask-secret", "env:SOME_OTHER_NAME", "--json"])
    assert result.exit_code == EXIT_USAGE, result.output
    error = json.loads(result.stdout)["error"]
    assert "exactly one place" in error and "--mask-secret" in error, error
    assert "SOME_OTHER_NAME" not in result.output and TEST_MASK_SECRET not in result.output
    assert not fresh.exists() and masked.read_bytes() == before
    assert not (tmp_path / "out.unmasked.csv").exists()


@pytest.mark.parametrize(
    ("command", "remedy"),
    [("run", guidance.RUN), ("unmask", guidance.UNMASK), ("report_vault", guidance.REPORT_VAULT)],
)
def test_no_secret_refuses_with_the_constant_remedy_before_any_output(
    tmp_path: Path, command: str, remedy: str
) -> None:
    """T-4a.1 / T-4a.2: text, --json and --quiet agree on the exit code; JSON carries the
    constant; nothing is written."""
    _, vault = _masked_run(tmp_path / "w", "yaml")
    masked = tmp_path / "w" / "out.csv"
    bare = _pipeline(tmp_path / "bare", ref=None)
    fresh = tmp_path / "fresh.bin"
    argv = _commands(bare, vault, masked, fresh)[command]
    text = runner.invoke(app, argv)
    as_json = runner.invoke(app, [*argv, "--json"])
    quiet = runner.invoke(app, [*argv, "--quiet"])
    assert text.exit_code == as_json.exit_code == quiet.exit_code == EXIT_USAGE, text.output
    assert json.loads(as_json.stdout)["error"] == remedy
    assert " ".join(remedy.split()) in " ".join(text.output.split())
    assert quiet.stdout == ""
    assert "--mask-secret" in remedy
    assert not fresh.exists() and not (tmp_path / "bare" / "out.csv").exists()
    assert not (tmp_path / "w" / "out.unmasked.csv").exists()


@pytest.mark.parametrize("args", [["unmask", "--help"], ["report", "vault", "--help"]])
def test_help_names_the_flag(args: list[str]) -> None:
    result = runner.invoke(app, args, env={"COLUMNS": "200"})
    assert result.exit_code == 0, result.output
    assert "--mask-secret" in result.output
    assert "same seed" not in " ".join(result.output.split())
