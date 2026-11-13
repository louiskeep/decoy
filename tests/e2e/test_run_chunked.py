"""`decoy run --chunked` (capability-gaps WS4, 2026-06-12).

Streams the source CSV through the engine chunk-by-chunk for inputs too
large for memory. The contract is byte parity with a plain run: chunked
mode only admits value-keyed strategies, so the output file must be
IDENTICAL bytes either way.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_USAGE
from tests.csv_sources import csv_source
from tests.keyed_secret import TEST_MASK_SECRET_REF

# Keyed strategies need an admitted mask secret (engine 0.17.0); see tests/keyed_secret.py.
pytestmark = pytest.mark.usefixtures("mask_secret")

runner = CliRunner()


_SOURCE_COLUMNS = ("ssn", "email")


def _undeclared_passthrough(columns: list[dict]) -> list[dict]:
    """The engine refuses a source column the config does not list; list the rest as passthrough."""
    declared = {c["name"] for c in columns}
    return [
        {"name": n, "strategy": "passthrough"} for n in _SOURCE_COLUMNS if n not in declared
    ]


def _pipeline(tmp_path: Path, columns: list[dict], rows: int = 200) -> Path:
    src = tmp_path / "in.csv"
    pd.DataFrame(
        {
            "ssn": [f"{i:09d}" for i in range(rows)],
            "email": [f"user{i}@example.com" for i in range(rows)],
        }
    ).to_csv(src, index=False)
    cfg = {
        "version": 2,
        "global_settings": {"seed": 42, "mask_secret_ref": TEST_MASK_SECRET_REF},
        "sources": {"accounts": csv_source(src)},
        "tables": [{"name": "accounts", "columns": [*columns, *_undeclared_passthrough(columns)]}],
        "targets": {
            "accounts": {
                "type": "file",
                "format": "csv",
                "path": str(tmp_path / "out.csv"),
            }
        },
    }
    p = tmp_path / "pipeline.yaml"
    p.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return p


_SAFE = [
    {
        "name": "ssn",
        "strategy": "fpe",
        "namespace": "ssn_ns",
        "provider_config": {"charset": "digits"},
    },
    {"name": "email", "strategy": "hash", "namespace": "email_ns"},
]


class TestRunChunked:
    def test_chunked_output_is_byte_identical_to_plain_run(
        self, tmp_path: Path
    ) -> None:
        cfg = _pipeline(tmp_path, _SAFE)
        assert runner.invoke(app, ["run", str(cfg)]).exit_code == 0
        plain = (tmp_path / "out.csv").read_bytes()
        (tmp_path / "out.csv").unlink()

        result = runner.invoke(
            app, ["run", str(cfg), "--chunked", "--chunk-size", "33"]
        )
        assert result.exit_code == 0, result.output
        assert (tmp_path / "out.csv").read_bytes() == plain

    def test_chunk_size_one(self, tmp_path: Path) -> None:
        cfg = _pipeline(tmp_path, _SAFE, rows=7)
        result = runner.invoke(app, ["run", str(cfg), "--chunked", "--chunk-size", "1"])
        assert result.exit_code == 0, result.output
        out = pd.read_csv(tmp_path / "out.csv", dtype=str)
        assert len(out) == 7
        assert out["ssn"].tolist() != [f"{i:09d}" for i in range(7)]

    def test_unsafe_strategy_exits_usage(self, tmp_path: Path) -> None:
        cfg = _pipeline(tmp_path, [{"name": "ssn", "strategy": "shuffle"}])
        result = runner.invoke(app, ["run", str(cfg), "--chunked"])
        assert result.exit_code == EXIT_USAGE
        assert "shuffle" in result.output and "value-keyed" in result.output

    def test_chunk_size_must_be_positive(self, tmp_path: Path) -> None:
        cfg = _pipeline(tmp_path, _SAFE)
        result = runner.invoke(app, ["run", str(cfg), "--chunked", "--chunk-size", "0"])
        assert result.exit_code != 0

    def test_deterministic_faker_chunked_matches_plain_run(
        self, tmp_path: Path
    ) -> None:
        """Deferred follow-up 2: deterministic faker with an explicit
        pool_size is admitted in chunked mode with byte parity."""
        columns = [
            {
                "name": "email",
                "strategy": "faker",
                "provider": "person_email",
                "deterministic": True,
                "namespace": "email_ns",
                "provider_config": {"pool_size": 25},
            },
            {"name": "ssn", "strategy": "hash", "namespace": "ssn_ns"},
        ]
        cfg = _pipeline(tmp_path, columns)
        assert runner.invoke(app, ["run", str(cfg)]).exit_code == 0
        plain = (tmp_path / "out.csv").read_bytes()
        (tmp_path / "out.csv").unlink()

        result = runner.invoke(
            app, ["run", str(cfg), "--chunked", "--chunk-size", "33"]
        )
        assert result.exit_code == 0, result.output
        assert (tmp_path / "out.csv").read_bytes() == plain

    def test_faker_without_pool_size_exits_usage(self, tmp_path: Path) -> None:
        columns = [
            {
                "name": "email",
                "strategy": "faker",
                "provider": "person_email",
                "deterministic": True,
                "namespace": "email_ns",
            }
        ]
        cfg = _pipeline(tmp_path, columns)
        result = runner.invoke(app, ["run", str(cfg), "--chunked"])
        assert result.exit_code == EXIT_USAGE
        assert "pool_size" in result.output


_CHUNKED_VAULT_REFUSAL = (
    "chunked runs cannot write a token vault; rerun without --chunked or without --vault"
)


@pytest.mark.parametrize("mode", ["text", "json"])
def test_chunked_with_vault_is_refused_before_any_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    """The engine (B-6) refuses a chunked entry with a vault writer: a chunked stream
    publishes output before the vault it re-identifies by exists. The CLI says so first,
    before admission, the vault writer or any engine entry runs."""
    import decoy_engine
    import decoy_engine.secret_providers

    calls: list[str] = []

    def _spy(name: str):
        def _called(*args, **kwargs):
            calls.append(name)
            raise AssertionError(f"{name} must not run")

        return _called

    for name in ("run_mask_pipeline_chunked", "run_pipeline", "vault_writer_for_config"):
        monkeypatch.setattr(decoy_engine, name, _spy(name))
    monkeypatch.setattr(decoy_engine.secret_providers, "admit_mask_key", _spy("admit_mask_key"))

    cfg = _pipeline(
        tmp_path, [{"name": "email", "strategy": "hash", "namespace": "e", "vault": True}]
    )
    vault = tmp_path / "vault.bin"
    argv = ["run", str(cfg), "--chunked", "--vault", str(vault)]
    result = runner.invoke(app, [*argv, "--json"] if mode == "json" else argv)

    assert result.exit_code == EXIT_USAGE, result.output
    assert calls == []
    assert not (tmp_path / "out.csv").exists()
    assert not vault.exists()
    if mode == "json":
        import json

        assert json.loads(result.stdout)["error"] == _CHUNKED_VAULT_REFUSAL
    else:
        assert _CHUNKED_VAULT_REFUSAL in " ".join(result.output.split())
