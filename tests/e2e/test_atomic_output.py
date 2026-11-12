"""A failed target write never leaves a partial or clobbered output (slice ATOMIC-OUTPUT).

Every test drives the CLI. A write that fails keeps the previous file byte-identical (or leaves
no file), makes no `.decoy-*.tmp` sibling, and exits the way the command always did.
"""

from __future__ import annotations

import errno
import hashlib
import os
import stat
from pathlib import Path
from typing import Any

import decoy_engine
import pandas as pd
import pyarrow.parquet as pq
import pytest
import yaml
from typer.testing import CliRunner

import decoy
from decoy.__main__ import app
from tests.csv_sources import file_source
from tests.keyed_secret import TEST_MASK_SECRET_REF

pytestmark = pytest.mark.usefixtures("mask_secret")

runner = CliRunner()
posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX file modes")

_ROWS = 5
_COLUMNS = [
    {"name": "id", "strategy": "passthrough"},
    {
        "name": "ssn",
        "strategy": "fpe",
        "namespace": "ssn_ns",
        "provider_config": {"charset": "digits"},
    },
    {"name": "email", "strategy": "hash", "namespace": "email_ns"},
]
_TOKEN_COLUMNS = [
    {"name": "id", "strategy": "passthrough"},
    {"name": "email", "strategy": "tokenize", "namespace": "people.email"},
]
_PRIOR = b"previous,good\n1,2\n"


def _source(tmp_path: Path, name: str = "in.csv") -> Path:
    src = tmp_path / name
    frame = pd.DataFrame(
        {
            "id": list(range(_ROWS)),
            "ssn": [f"{i:09d}" for i in range(_ROWS)],
            "email": [f"user{i}@example.com" for i in range(_ROWS)],
        }
    )
    if src.suffix == ".parquet":
        frame.to_parquet(src, index=False)
    else:
        frame.to_csv(src, index=False)
    return src


def _config(
    tmp_path: Path,
    *,
    out: str = "out.csv",
    fmt: str = "csv",
    columns: list[dict[str, Any]] | None = None,
    src: Path | None = None,
) -> Path:
    src = src or _source(tmp_path)
    cfg = {
        "version": 2,
        "global_settings": {"seed": 42, "mask_secret_ref": TEST_MASK_SECRET_REF},
        "sources": {"people": file_source(src, src.suffix.lstrip(".") or "csv")},
        "tables": [{"name": "people", "columns": columns or _COLUMNS}],
        "targets": {"people": {"type": "file", "format": fmt, "path": str(tmp_path / out)}},
    }
    path = tmp_path / "pipeline.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _run(cfg: Path, *args: str) -> Any:
    return runner.invoke(app, ["run", str(cfg), *args])


def _chunked(cfg: Path, *args: str) -> Any:
    return _run(cfg, "--chunked", "--chunk-size", "2", *args)


def _temps(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.iterdir() if ".decoy-" in p.name)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fail_after_first_chunk(monkeypatch: pytest.MonkeyPatch, exc: BaseException) -> None:
    real = decoy_engine.run_mask_pipeline_chunked

    def patched(*args: Any, **kwargs: Any) -> Any:
        chunks = real(*args, **kwargs)

        def gen() -> Any:
            yield next(chunks)
            raise exc

        return gen()

    monkeypatch.setattr(decoy_engine, "run_mask_pipeline_chunked", patched)


# -- AT-A1, AT-A2: chunked writers ---------------------------------------------------------


@pytest.mark.parametrize("prior", [None, _PRIOR])
def test_chunked_csv_failure_after_chunk_one_keeps_the_prior_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, prior: bytes | None
) -> None:
    cfg = _config(tmp_path)
    target = tmp_path / "out.csv"
    if prior is not None:
        target.write_bytes(prior)
    _fail_after_first_chunk(monkeypatch, RuntimeError("boom"))
    result = _chunked(cfg)
    assert result.exit_code == 3, result.output
    assert "error:" in result.output
    assert (target.read_bytes() if prior is not None else None) == prior
    assert prior is not None or not target.exists()
    assert _temps(tmp_path) == []


@pytest.mark.parametrize("prior", [None, b"PAR1 not really"])
def test_chunked_parquet_failure_after_chunk_one_keeps_the_prior_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, prior: bytes | None
) -> None:
    cfg = _config(tmp_path, out="out.parquet", fmt="parquet")
    target = tmp_path / "out.parquet"
    if prior is not None:
        target.write_bytes(prior)
    _fail_after_first_chunk(monkeypatch, RuntimeError("boom"))
    result = _chunked(cfg)
    assert result.exit_code == 3, result.output
    assert (target.read_bytes() if prior is not None else None) == prior
    assert prior is not None or not target.exists()
    assert _temps(tmp_path) == []


# -- AT-A3: whole-table write --------------------------------------------------------------


@pytest.mark.parametrize("prior", [None, _PRIOR])
def test_whole_table_write_failure_keeps_the_prior_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, prior: bytes | None
) -> None:
    cfg = _config(tmp_path)
    target = tmp_path / "out.csv"
    if prior is not None:
        target.write_bytes(prior)

    def half_then_raise(self: pd.DataFrame, path: Any, *args: Any, **kwargs: Any) -> None:
        Path(path).write_text("half")
        raise OSError(errno.ENOSPC, "no space")

    monkeypatch.setattr(pd.DataFrame, "to_csv", half_then_raise)
    result = _run(cfg)
    assert result.exit_code == 3, result.output
    assert (target.read_bytes() if prior is not None else None) == prior
    assert prior is not None or not target.exists()
    assert _temps(tmp_path) == []


# -- AT-A4: interrupt ----------------------------------------------------------------------


def test_an_interrupt_during_a_chunked_write_keeps_the_prior_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _config(tmp_path)
    target = tmp_path / "out.csv"
    target.write_bytes(_PRIOR)
    _fail_after_first_chunk(monkeypatch, KeyboardInterrupt())
    result = _chunked(cfg)
    assert result.exit_code == 130  # Click reports an interrupt as SIGINT
    assert target.read_bytes() == _PRIOR
    assert _temps(tmp_path) == []


# -- AT-A9: empty source -------------------------------------------------------------------


def test_a_chunked_source_that_yields_nothing_leaves_the_prior_output_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pin: nothing is written today either. Its strength comes from the stage-before-peek
    mutation, which would replace the prior output with an empty file."""
    cfg = _config(tmp_path)
    target = tmp_path / "out.csv"
    target.write_bytes(_PRIOR)
    monkeypatch.setattr(decoy_engine, "run_mask_pipeline_chunked", lambda *a, **k: iter(()))
    result = _chunked(cfg)
    assert result.exit_code == 0, result.output
    assert target.read_bytes() == _PRIOR
    assert _temps(tmp_path) == []


def test_an_empty_parquet_source_still_writes_a_zero_row_parquet(tmp_path: Path) -> None:
    src = tmp_path / "in.parquet"
    _source(tmp_path, "full.parquet")
    pq.write_table(pq.read_table(tmp_path / "full.parquet").slice(0, 0), src)
    cfg = _config(tmp_path, out="out.parquet", fmt="parquet", src=src)
    result = _chunked(cfg)
    assert result.exit_code == 0, result.output
    assert pq.read_table(tmp_path / "out.parquet").num_rows == 0
    assert _temps(tmp_path) == []


# -- AT-A5: success bytes are the base's ---------------------------------------------------

# sha256 of each output, recorded on CLI main ff82bc9 before this slice.
_BASE_SHA: dict[str, str] = {
    "chunked_csv": "f9987e148964006181da8b39f71723fc5f85bc3dd73768ad9f9d6d50d177a9b8",
    "chunked_parquet": "b0683c6a777c6eed16efa729aa8816be938cc545efd43a9a92d050115a7e663d",
    "demo": "d784565e2ae6bc228f266b8080ad49ab3fd80ee94269f7b7261f79e624723011",
    "detokenize": "22bc0317beeb6d82d44f6e003f9441d41e63e9efd59122173a11393b425fc909",
    "mask_api": "f9987e148964006181da8b39f71723fc5f85bc3dd73768ad9f9d6d50d177a9b8",
    "run_csv": "f9987e148964006181da8b39f71723fc5f85bc3dd73768ad9f9d6d50d177a9b8",
    "run_parquet": "fbaa202d72c0db74793d4b068ae984abe3919d95062cc7ca0e7ead23c0f74f1a",
    "tokenize": "a43f8eb615952715b2d7c6c836e4516efb66e87d5b8f008be14a236039dc71aa",
    "unmask": "f02d2dca5c249826e217b8aaa531146f8d99a4dff1e6cae2555efdbcb55b5ed1",
}


def _success_outputs(tmp_path: Path) -> dict[str, str]:
    got: dict[str, str] = {}
    for label, fmt, flags in [
        ("run_csv", "csv", ()),
        ("run_parquet", "parquet", ()),
        ("chunked_csv", "csv", ("--chunked", "--chunk-size", "2")),
        ("chunked_parquet", "parquet", ("--chunked", "--chunk-size", "2")),
    ]:
        work = tmp_path / label
        work.mkdir()
        out = f"out.{'parquet' if fmt == 'parquet' else 'csv'}"
        result = _run(_config(work, out=out, fmt=fmt), *flags)
        assert result.exit_code == 0, result.output
        got[label] = _sha(work / out)
    work = tmp_path / "tok"
    work.mkdir()
    cfg = _config(work, columns=_TOKEN_COLUMNS, out="tokenized.csv")
    vault = work / "tokens.db"
    assert runner.invoke(app, ["tokenize", str(cfg), "--vault", str(vault)]).exit_code == 0
    got["tokenize"] = _sha(work / "tokenized.csv")
    result = runner.invoke(
        app, ["detokenize", str(cfg), str(work / "tokenized.csv"), "--vault", str(vault)]
    )
    assert result.exit_code == 0, result.output
    got["detokenize"] = _sha(work / "tokenized.detokenized.csv")
    work = tmp_path / "unm"
    work.mkdir()
    cfg = _config(work)
    assert _run(cfg).exit_code == 0
    unmasked = work / "unmasked.csv"
    result = runner.invoke(app, ["unmask", str(cfg), str(work / "out.csv"), "-o", str(unmasked)])
    assert result.exit_code == 0, result.output
    got["unmask"] = _sha(unmasked)
    work = tmp_path / "api"
    work.mkdir()
    cfg = _config(work)
    decoy.mask(config=str(cfg), out=str(work / "api.csv"))
    got["mask_api"] = _sha(work / "api.csv")
    work = tmp_path / "demo"
    result = runner.invoke(app, ["demo", "--dir", str(work)])
    assert result.exit_code == 0, result.output
    got["demo"] = _sha(work / "customers_masked.csv")
    return got


def test_success_outputs_are_byte_identical_to_the_base(tmp_path: Path) -> None:
    """Pin: green on the base and on head."""
    got = _success_outputs(tmp_path)
    assert got == _BASE_SHA, got


# -- AT-A6: permissions --------------------------------------------------------------------


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


@pytest.fixture
def umask() -> Any:
    previous = os.umask(0o022)
    yield lambda value: os.umask(value)
    os.umask(previous)


@posix_only
@pytest.mark.parametrize("mask", [0o022, 0o077])
def test_new_masked_output_gets_the_umask_default(tmp_path: Path, umask: Any, mask: int) -> None:
    cfg = _config(tmp_path)
    umask(mask)
    assert _run(cfg).exit_code == 0
    assert _mode(tmp_path / "out.csv") == 0o666 & ~mask


@posix_only
@pytest.mark.parametrize("chunked", [False, True])
def test_an_extreme_umask_still_lets_the_run_finish(
    tmp_path: Path, umask: Any, chunked: bool
) -> None:
    cfg = _config(tmp_path)
    umask(0o277)
    result = _chunked(cfg) if chunked else _run(cfg)
    assert result.exit_code == 0, result.output
    assert _mode(tmp_path / "out.csv") == 0o666 & ~0o277


@posix_only
@pytest.mark.parametrize("bits", [0o600, 0o400, 0o640])
@pytest.mark.parametrize("chunked", [False, True])
def test_a_masked_rerun_keeps_the_existing_output_bits(
    tmp_path: Path, bits: int, chunked: bool
) -> None:
    cfg = _config(tmp_path)
    target = tmp_path / "out.csv"
    target.write_bytes(_PRIOR)
    target.chmod(bits)
    result = _chunked(cfg) if chunked else _run(cfg)
    assert result.exit_code == 0, result.output
    assert target.read_bytes() != _PRIOR
    assert _mode(target) == bits


@posix_only
def test_unmask_and_detokenize_outputs_are_owner_only(tmp_path: Path, umask: Any) -> None:
    cfg = _config(tmp_path)
    assert _run(cfg).exit_code == 0
    unmasked = tmp_path / "unmasked.csv"
    result = runner.invoke(
        app, ["unmask", str(cfg), str(tmp_path / "out.csv"), "-o", str(unmasked)]
    )
    assert result.exit_code == 0, result.output
    assert _mode(unmasked) == 0o600
    tok = tmp_path / "tok"
    tok.mkdir()
    tcfg = _config(tok, columns=_TOKEN_COLUMNS, out="tokenized.csv")
    vault = tok / "tokens.db"
    assert runner.invoke(app, ["tokenize", str(tcfg), "--vault", str(vault)]).exit_code == 0
    assert _mode(tok / "tokenized.csv") == 0o666 & ~0o022
    result = runner.invoke(
        app, ["detokenize", str(tcfg), str(tok / "tokenized.csv"), "--vault", str(vault)]
    )
    assert result.exit_code == 0, result.output
    assert _mode(tok / "tokenized.detokenized.csv") == 0o600


# -- AT-A7 (CLI): a symlinked target ------------------------------------------------------


@posix_only
@pytest.mark.parametrize("chunked", [False, True])
@pytest.mark.parametrize("dangling", [False, True])
def test_a_symlinked_target_updates_its_destination(
    tmp_path: Path, chunked: bool, dangling: bool
) -> None:
    cfg = _config(tmp_path)
    dest = tmp_path / "elsewhere.csv"
    if not dangling:
        dest.write_bytes(_PRIOR)
    (tmp_path / "out.csv").symlink_to(dest)
    result = _chunked(cfg) if chunked else _run(cfg)
    assert result.exit_code == 0, result.output
    assert (tmp_path / "out.csv").is_symlink()
    assert pd.read_csv(dest, dtype=str).shape[0] == _ROWS
    assert _temps(tmp_path) == []


# -- AT-A12: in-memory output writes -------------------------------------------------------


def _artifact_cases(tmp_path: Path) -> dict[str, tuple[list[str], int]]:
    """CLI argument lists that each write one artifact at `tmp_path/'artifact.out'`."""
    cfg = _config(tmp_path)
    ev = tmp_path / "evidence.json"
    assert _run(cfg, "--evidence-out", str(ev)).exit_code == 0
    masked, src, art = (
        str(tmp_path / "out.csv"),
        str(tmp_path / "in.csv"),
        str(tmp_path / "artifact.out"),
    )
    return {
        "fit": (["fit", src, "-o", art], 3),
        "scan": (["scan", src, "--has-header", "-o", art], 3),
        "evidence": (["run", str(cfg), "--evidence-out", art], 3),
        "report_render": (["report", "render", str(ev), "-o", art], 1),
        "report_show": (["report", "show", str(ev), "--format", "markdown", "-o", art], 1),
        "fidelity": (["report", "fidelity", src, masked, "--report-out", art], 1),
        "integrity": (["report", "integrity", masked, "--source", src, "-o", art], 1),
    }


_ARTIFACTS = ["fit", "scan", "evidence", "report_render", "report_show", "fidelity", "integrity"]


@pytest.mark.parametrize("name", _ARTIFACTS)
def test_an_artifact_write_failure_keeps_the_prior_file_and_renders_the_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    args, exit_code = _artifact_cases(tmp_path)[name]
    art = tmp_path / "artifact.out"
    art.write_bytes(b"previous artifact")
    real = os.replace

    def fail_for_the_artifact(src: Any, dst: Any) -> None:
        if Path(dst).name == "artifact.out":
            raise OSError(errno.EIO, "disk says no", str(dst))
        real(src, dst)

    monkeypatch.setattr(os, "replace", fail_for_the_artifact)
    result = runner.invoke(app, args)
    assert result.exit_code == exit_code, result.output
    flat = " ".join(result.output.split())
    assert f"atomic_write_failed ({os.strerror(errno.EIO)})" in flat, result.output
    assert art.read_bytes() == b"previous artifact"
    assert _temps(tmp_path) == []


@posix_only
@pytest.mark.parametrize("name", _ARTIFACTS)
def test_an_artifact_is_owner_only_and_follows_a_symlink(tmp_path: Path, name: str) -> None:
    args, _exit = _artifact_cases(tmp_path)[name]
    art = tmp_path / "artifact.out"
    dest = tmp_path / "linked-dest"
    art.symlink_to(dest)
    previous = os.umask(0o022)
    try:
        result = runner.invoke(app, args)
    finally:
        os.umask(previous)
    assert result.exit_code in (0, 2), result.output
    assert art.is_symlink() and dest.stat().st_size > 0
    assert _mode(dest) == 0o600
    assert _temps(tmp_path) == []


# -- AT-A13 (CLI): compression ------------------------------------------------------------


@pytest.mark.parametrize("chunked", [False, True])
def test_gz_csv_target_stays_gzip_and_decodes_to_the_plain_csv(
    tmp_path: Path, chunked: bool
) -> None:
    import gzip

    plain = tmp_path / "plain"
    plain.mkdir()
    zipped = tmp_path / "zipped"
    zipped.mkdir()
    args = ("--chunked", "--chunk-size", "2") if chunked else ()
    assert _run(_config(plain), *args).exit_code == 0
    assert _run(_config(zipped, out="out.csv.gz"), *args).exit_code == 0
    raw = (zipped / "out.csv.gz").read_bytes()
    assert raw[:2] == b"\x1f\x8b"
    assert gzip.decompress(raw) == (plain / "out.csv").read_bytes()
    assert _temps(zipped) == []


@pytest.mark.parametrize("suffix", [".csv.zip", ".csv.tar.gz"])
def test_archive_targets_hold_one_member_named_after_the_real_target(
    tmp_path: Path, suffix: str
) -> None:
    import tarfile
    import zipfile

    plain = tmp_path / "plain"
    plain.mkdir()
    arch = tmp_path / "arch"
    arch.mkdir()
    assert _run(_config(plain)).exit_code == 0
    assert _run(_config(arch, out=f"out{suffix}")).exit_code == 0
    target = arch / f"out{suffix}"
    if suffix.endswith(".zip"):
        with zipfile.ZipFile(target) as archive:
            assert archive.namelist() == ["out.csv"]
            member = archive.read("out.csv")
    else:
        assert target.read_bytes()[:2] == b"\x1f\x8b"
        with tarfile.open(target, "r:gz") as archive:
            assert archive.getnames() == ["out.csv"]
            handle = archive.extractfile("out.csv")
            assert handle is not None
            member = handle.read()
    assert member == (plain / "out.csv").read_bytes()
    assert _temps(arch) == []
