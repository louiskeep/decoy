"""`decoy run --chunked` (capability-gaps WS4, 2026-06-12).

Streams the source CSV through the engine chunk-by-chunk for inputs too
large for memory. The contract is byte parity with a plain run: chunked
mode only admits value-keyed strategies, so the output file must be
IDENTICAL bytes either way.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_USAGE

runner = CliRunner()


def _pipeline(tmp_path: Path, columns: list[dict], rows: int = 200) -> Path:
    src = tmp_path / "in.csv"
    pd.DataFrame(
        {
            "ssn": [f"{i:09d}" for i in range(rows)],
            "email": [f"user{i}@example.com" for i in range(rows)],
        }
    ).to_csv(src, index=False)
    cfg = {
        "version": 1,
        "global_settings": {"seed": 42},
        "sources": {"accounts": {"type": "file", "format": "csv", "path": str(src)}},
        "tables": [{"name": "accounts", "columns": columns}],
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
    def test_chunked_output_is_byte_identical_to_plain_run(self, tmp_path: Path) -> None:
        cfg = _pipeline(tmp_path, _SAFE)
        assert runner.invoke(app, ["run", str(cfg)]).exit_code == 0
        plain = (tmp_path / "out.csv").read_bytes()
        (tmp_path / "out.csv").unlink()

        result = runner.invoke(app, ["run", str(cfg), "--chunked", "--chunk-size", "33"])
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

    def test_deterministic_faker_chunked_matches_plain_run(self, tmp_path: Path) -> None:
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

        result = runner.invoke(app, ["run", str(cfg), "--chunked", "--chunk-size", "33"])
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
