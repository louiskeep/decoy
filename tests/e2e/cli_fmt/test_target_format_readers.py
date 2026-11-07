"""CLI-written files are read back by the format they were written in (CLI-FMT Part B).

`decoy detokenize`, `decoy unmask` and `decoy report diff` read files the CLI wrote. After
Part A those files hold their target's declared format, so a reader that keys on the suffix
reads Parquet-at-`.pq` and fixed width as CSV. Every assertion is on exit codes and recovered
values compared exactly with the source.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.evidence import build_manifest, compute_manifest_hash
from decoy.cli.exit_codes import EXIT_RUNTIME, EXIT_USAGE
from tests.e2e.cli_fmt.test_target_format_dispatch import _csv_config, _target, _target_layout
from tests.e2e.test_source_format_dispatch import _COLUMNS, _PEOPLE
from tests.e2e.test_tokenize_cli import _TOKENIZE_COLS
from tests.e2e.test_tokenize_cli import _pipeline as _tokenize_pipeline
from tests.keyed_secret import TEST_MASK_SECRET_REF

pytestmark = pytest.mark.usefixtures("mask_secret")
needs_vault = pytest.mark.skipif(
    importlib.util.find_spec("cryptography") is None, reason="the vault needs cryptography"
)

runner = CliRunner()
_EMAILS = ["a@x.com", "b@y.com", "a@x.com"]
_VAULT_EMAILS = [f"user{i}@example.com" for i in range(5)]
_CELL = "ZQ9cell"


# ---------------------------------------------------------------------------
# detokenize (R1)
# ---------------------------------------------------------------------------


def _set_layout(config: Path, layout: dict[str, Any]) -> None:
    raw = yaml.safe_load(config.read_text(encoding="utf-8"))
    raw["targets"]["people"]["layout"] = layout
    config.write_text(yaml.safe_dump(raw), encoding="utf-8")


def _token_width(tmp_path: Path) -> int:
    """The length of one token, measured from a CSV tokenize run in a sibling folder."""
    probe = tmp_path / "probe"
    probe.mkdir()
    cfg = _tokenize_pipeline(probe, _TOKENIZE_COLS)
    assert runner.invoke(app, ["tokenize", str(cfg), "--vault", str(probe / "v.db")]).exit_code == 0
    return int(pd.read_csv(probe / "tokenized.csv", dtype=str)["email"].str.len().max())


def _fw_layout(width: int) -> dict[str, Any]:
    return {
        "columns": [
            {"name": "id", "start": 0, "width": 1},
            {"name": "email", "start": 1, "width": width},
        ]
    }


def _tokenize(d: Path, name: str, fmt: str, layout: dict | None = None) -> tuple[Path, Path]:
    d.mkdir(exist_ok=True)
    cfg = _tokenize_pipeline(d, _TOKENIZE_COLS, out_name=name, out_format=fmt, emails=_EMAILS)
    if layout is not None:
        _set_layout(cfg, layout)
    vault = d / "tokens.db"
    result = runner.invoke(app, ["tokenize", str(cfg), "--vault", str(vault)])
    assert result.exit_code == 0, result.output
    return cfg, vault


def _detok(cfg: Path, src: Path, vault: Path, *args: str) -> Any:
    return runner.invoke(app, ["detokenize", str(cfg), str(src), "--vault", str(vault), *args])


def test_detokenize_parquet_pq_round_trip(tmp_path: Path) -> None:
    cfg, vault = _tokenize(tmp_path, "tok.pq", "parquet")
    result = _detok(cfg, tmp_path / "tok.pq", vault)
    assert result.exit_code == 0, result.output
    got = pd.read_parquet(tmp_path / "tok.detokenized.parquet")
    assert got["email"].tolist() == _EMAILS


def test_detokenize_fixed_width_round_trip(tmp_path: Path) -> None:
    layout = _fw_layout(_token_width(tmp_path))
    cfg, vault = _tokenize(tmp_path, "tok.txt", "fixed_width", layout)
    result = _detok(cfg, tmp_path / "tok.txt", vault)
    assert result.exit_code == 0, result.output
    got = pd.read_csv(tmp_path / "tok.detokenized.csv", dtype=str)
    assert got["email"].tolist() == _EMAILS
    assert got["id"].tolist() == ["0", "1", "2"]


def test_fixed_width_tokenize_refused_before_any_file(tmp_path: Path) -> None:
    layout = _fw_layout(_token_width(tmp_path) - 1)
    d = tmp_path / "narrow"
    d.mkdir()
    cfg = _tokenize_pipeline(d, _TOKENIZE_COLS, out_name="tok.txt", out_format="fixed_width")
    _set_layout(cfg, layout)
    result = runner.invoke(app, ["tokenize", str(cfg), "--vault", str(d / "v.db")])
    assert result.exit_code == EXIT_RUNTIME, result.output
    assert [p.name for p in d.iterdir() if "tok.txt" in p.name] == []
    assert "tok_" not in result.output
    assert "a@x.com" not in result.output


def test_reader_off_target_uses_suffix(tmp_path: Path) -> None:
    cfg, vault = _tokenize(tmp_path / "pq", "tok.pq", "parquet")
    copy_pq = tmp_path / "pq" / "copy.pq"
    shutil.copy(tmp_path / "pq" / "tok.pq", copy_pq)
    result = _detok(cfg, copy_pq, vault)
    assert result.exit_code == 0, result.output
    got = pd.read_parquet(tmp_path / "pq" / "copy.detokenized.parquet")
    assert got["email"].tolist() == _EMAILS

    cfg, vault = _tokenize(tmp_path / "csv", "tok.csv", "csv")
    copy_dat = tmp_path / "csv" / "copy.dat"
    shutil.copy(tmp_path / "csv" / "tok.csv", copy_dat)
    result = _detok(cfg, copy_dat, vault)
    assert result.exit_code == 0, result.output
    got_csv = pd.read_csv(tmp_path / "csv" / "copy.detokenized.csv", dtype=str)
    assert got_csv["email"].tolist() == _EMAILS


# ---------------------------------------------------------------------------
# unmask (R2)
# ---------------------------------------------------------------------------


def _vault_config(d: Path, target: dict[str, Any]) -> Path:
    d.mkdir(exist_ok=True)
    src = d / "accounts.csv"
    pd.DataFrame(
        {
            "id": [f"r{i}" for i in range(5)],
            "email": _VAULT_EMAILS,
            "name": [f"Person {i}" for i in range(5)],
        }
    ).to_csv(src, index=False)
    cfg = {
        "version": 2,
        "global_settings": {"seed": 42, "mask_secret_ref": TEST_MASK_SECRET_REF},
        "sources": {"accounts": {"type": "file", "format": "csv", "path": str(src)}},
        "tables": [
            {
                "name": "accounts",
                "columns": [
                    {"name": "id", "strategy": "passthrough"},
                    {"name": "email", "strategy": "hash", "namespace": "email_ns", "vault": True},
                    {"name": "name", "strategy": "redact"},
                ],
            }
        ],
        "targets": {"accounts": {"type": "file", **target}},
    }
    path = d / "pipeline.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _masked_vault_run(d: Path, target: dict[str, Any]) -> tuple[Path, Path]:
    cfg = _vault_config(d, target)
    vault = d / "vault.bin"
    result = runner.invoke(app, ["run", str(cfg), "--vault", str(vault)])
    assert result.exit_code == 0, result.output
    return cfg, vault


def _unmask(cfg: Path, masked: Path, vault: Path, out: Path) -> Any:
    args = ["unmask", str(cfg), str(masked), "--vault", str(vault), "-o", str(out)]
    return runner.invoke(app, args)


def _assert_unmasked(out: Path, masked: pd.DataFrame) -> None:
    got = pd.read_csv(out, dtype=str)
    assert got["email"].tolist() == _VAULT_EMAILS
    assert got["id"].tolist() == masked["id"].tolist()
    assert got["name"].tolist() == masked["name"].tolist()


def _vault_layout(d: Path) -> dict[str, Any]:
    """A layout sized from the masked frame, every column `str` (hash tokens overflow `_LAYOUT`)."""
    probe = d / "probe"
    _masked_vault_run(probe, {"format": "csv", "path": str(probe / "m.csv")})
    layout = _target_layout(pd.read_csv(probe / "m.csv", dtype=str))
    return {"columns": [{**c, "type": "str"} for c in layout["columns"]]}


@needs_vault
def test_unmask_parquet_target_at_dat(tmp_path: Path) -> None:
    cfg, vault = _masked_vault_run(tmp_path, _target("parquet", tmp_path / "m.dat"))
    masked = pd.read_parquet(tmp_path / "m.dat")
    result = _unmask(cfg, tmp_path / "m.dat", vault, tmp_path / "rec.csv")
    assert result.exit_code == 0, result.output
    _assert_unmasked(tmp_path / "rec.csv", masked)


@needs_vault
def test_unmask_fixed_width_target(tmp_path: Path) -> None:
    layout = _vault_layout(tmp_path)
    target = _target("fixed_width", tmp_path / "m.txt", layout)
    cfg, vault = _masked_vault_run(tmp_path, target)
    from decoy_engine import read_fixed_width

    masked = read_fixed_width(tmp_path / "m.txt", layout)
    result = _unmask(cfg, tmp_path / "m.txt", vault, tmp_path / "rec.csv")
    assert result.exit_code == 0, result.output
    _assert_unmasked(tmp_path / "rec.csv", masked)


def _config_naming(cfg: Path, table: str, path: Path, dest: Path) -> Path:
    raw = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    raw["targets"][table]["path"] = str(path)
    dest.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return dest


@needs_vault
@pytest.mark.skipif(not hasattr(Path, "symlink_to"), reason="needs symlinks")
def test_reader_match_through_symlinked_dir(tmp_path: Path) -> None:
    # Fixed-width tokenize target: the YAML names link/, the argument names real/, and back.
    real, link = tmp_path / "real", tmp_path / "link"
    real.mkdir()
    link.symlink_to(real, target_is_directory=True)
    layout = _fw_layout(_token_width(tmp_path))
    cfg_link, vault = _tokenize(tmp_path, "link/tok.txt", "fixed_width", layout)
    cfg_real = _config_naming(cfg_link, "people", real / "tok.txt", tmp_path / "pipeline_real.yaml")
    for n, (cfg, arg) in enumerate(((cfg_link, real), (cfg_real, link))):
        out = tmp_path / f"detok{n}.csv"
        result = _detok(cfg, arg / "tok.txt", vault, "-o", str(out))
        assert result.exit_code == 0, result.output
        assert pd.read_csv(out, dtype=str)["email"].tolist() == _EMAILS

    # Parquet-at-.dat masked target, the same two directions.
    u_dir = tmp_path / "u"
    u_real, u_link = u_dir / "real", u_dir / "link"
    u_real.mkdir(parents=True)
    u_link.symlink_to(u_real, target_is_directory=True)
    cfg_link, vault = _masked_vault_run(u_dir, _target("parquet", u_link / "m.dat"))
    masked = pd.read_parquet(u_real / "m.dat")
    cfg_real = _config_naming(cfg_link, "accounts", u_real / "m.dat", u_dir / "pipeline_real.yaml")
    for n, (cfg, arg) in enumerate(((cfg_link, u_real), (cfg_real, u_link))):
        out = u_dir / f"rec{n}.csv"
        result = _unmask(cfg, arg / "m.dat", vault, out)
        assert result.exit_code == 0, result.output
        _assert_unmasked(out, masked)


# ---------------------------------------------------------------------------
# evidence manifest and report diff (R3)
# ---------------------------------------------------------------------------


def _people_config(d: Path, target: dict[str, Any], rows: list[tuple] = _PEOPLE) -> Path:
    d.mkdir(exist_ok=True)
    src = d / "people.csv"
    pd.DataFrame(rows, columns=["id", "name", "age"]).to_csv(src, index=False)
    cfg = {
        "version": 2,
        "global_settings": {"seed": 42, "mask_secret_ref": TEST_MASK_SECRET_REF},
        "sources": {"people": {"type": "file", "format": "csv", "path": str(src)}},
        "tables": [{"name": "people", "columns": _COLUMNS}],
        "targets": {"people": {"type": "file", **target}},
    }
    path = d / "pipeline.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _run_evidence(config: Path, evidence: Path) -> dict[str, Any]:
    result = runner.invoke(app, ["run", str(config), "--evidence-out", str(evidence)])
    assert result.exit_code == 0, result.output
    return json.loads(evidence.read_text(encoding="utf-8"))


def _run_people(d: Path, target: dict[str, Any], evidence: Path, rows: list[tuple] = _PEOPLE):
    return _run_evidence(_people_config(d, target, rows), evidence)


def _fixed_width_layout(d: Path) -> dict[str, Any]:
    probe = d / "probe"
    _run_people(probe, _target("csv", probe / "m.csv"), d / "e0.json")
    return _target_layout(pd.read_csv(probe / "m.csv", dtype=str))


def test_manifest_records_format_and_layout(tmp_path: Path) -> None:
    layout = _fixed_width_layout(tmp_path)
    targets = {
        "a": _target("csv", tmp_path / "a.csv"),
        "b": _target("parquet", tmp_path / "b.pq"),
        "c": _target("fixed_width", tmp_path / "c.txt", layout),
    }
    config = _csv_config(tmp_path, targets)
    manifest = _run_evidence(config, tmp_path / "ev.json")
    entries = manifest["output_fingerprints"]
    assert manifest["schema_version"] == "cli-local-1"
    assert {k: v.get("format") for k, v in entries.items()} == {
        "a": "csv",
        "b": "parquet",
        "c": "fixed_width",
    }
    assert "layout" not in entries["a"] and "layout" not in entries["b"]
    from decoy_engine import PipelineConfig

    validated = PipelineConfig.model_validate(yaml.safe_load(config.read_text(encoding="utf-8")))
    assert entries["c"]["layout"] == validated.model_dump()["targets"]["c"]["layout"]
    verify = runner.invoke(app, ["report", "verify", str(tmp_path / "ev.json")])
    assert verify.exit_code == 0, verify.output


def _diff(a: Path, b: Path, *args: str) -> Any:
    return runner.invoke(app, ["report", "diff", str(a), str(b), "--json", *args])


def _data_level(a: Path, b: Path) -> dict[str, Any]:
    result = _diff(a, b)
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["data_level"] == "compared", payload
    return {"change": payload["any_data_change"], "deltas": payload["table_deltas"]}


def _pair(d: Path, name: str, fmt: str) -> tuple[Path, Path]:
    paths = []
    for side in ("a", "b"):
        sub = d / side
        sub.mkdir(parents=True, exist_ok=True)
        _run_people(sub, _target(fmt, sub / name), d / f"ev_{side}.json")
        paths.append(d / f"ev_{side}.json")
    return paths[0], paths[1]


@pytest.mark.parametrize("name", ["x.pq", "x.dat", "x_no_suffix"])
def test_report_diff_parquet_at_pq_dat_and_no_suffix(tmp_path: Path, name: str) -> None:
    base = _data_level(*_pair(tmp_path / "ref", "x.parquet", "parquet"))
    assert base["change"] is False
    assert [d["row_count_a"] for d in base["deltas"]] == [3]
    assert _data_level(*_pair(tmp_path / "got", name, "parquet")) == base


def test_report_diff_fixed_width_both_sides(tmp_path: Path) -> None:
    layout = _fixed_width_layout(tmp_path)
    changed = [_PEOPLE[0], ("A00002", "Alice", 4), _PEOPLE[2]]
    runs = {}
    for side, rows in (("a", _PEOPLE), ("b", changed)):
        sub = tmp_path / side
        target = _target("fixed_width", sub / "out.txt", layout)
        _run_people(sub, target, tmp_path / f"ev_{side}.json", rows)
        runs[side] = tmp_path / f"ev_{side}.json"
    first = _data_level(runs["a"], runs["b"])
    assert first["change"] is True
    (delta,) = first["deltas"]
    assert delta["row_count_delta"] == 0
    assert [(c["column"], c["unique_count_delta"]) for c in delta["column_deltas"]] == [
        ("name", -1)
    ]
    # The manifest alone decides: an edited pipeline copy, then no pipeline file at all.
    for side in ("a", "b"):
        pipeline = tmp_path / side / "pipeline.yaml"
        edited = yaml.safe_load(pipeline.read_text(encoding="utf-8"))
        edited["targets"]["people"] = {"type": "file", "format": "csv", "path": "x.csv"}
        pipeline.write_text(yaml.safe_dump(edited), encoding="utf-8")
    assert _data_level(runs["a"], runs["b"]) == first
    for side in ("a", "b"):
        (tmp_path / side / "pipeline.yaml").unlink()
    assert _data_level(runs["a"], runs["b"]) == first


def _manifest(d: Path, tag: str, out: Path, fmt: str) -> dict[str, Any]:
    pipeline = d / f"pipeline_{tag}.yaml"
    pipeline.write_text("version: 2\n", encoding="utf-8")
    config = {"targets": {"t": {"type": "file", "format": fmt, "path": str(out)}}}
    return build_manifest(
        pipeline_path=pipeline,
        config_dict=config,
        run_result={"row_counts": {"t": 2}},
        cli_version="0",
        engine_version="0",
    )


def _write_manifest(dest: Path, manifest: dict[str, Any], **entry: Any) -> Path:
    """Write `manifest` with `entry` keys set on its output (None removes a key), hash redone."""
    manifest = copy.deepcopy(manifest)
    merged = {**manifest["output_fingerprints"]["t"], **entry}
    manifest["output_fingerprints"]["t"] = {k: v for k, v in merged.items() if v is not None}
    manifest["manifest_hash"] = compute_manifest_hash(manifest)
    dest.write_text(json.dumps(manifest), encoding="utf-8")
    return dest


def _old_shape(path: Path, manifest: dict[str, Any]) -> Path:
    """The manifest as the CLI wrote it before this slice: no `format`, no `layout`."""
    return _write_manifest(path, manifest, format=None, layout=None)


_FRAME = pd.DataFrame({"id": ["1", "2"], "name": ["Al", "Bo"]})


def test_report_diff_old_manifest_falls_back(tmp_path: Path) -> None:
    for kind, write in (("parquet", _FRAME.to_parquet), ("csv", _FRAME.to_csv)):
        sides = []
        for tag in ("a", "b"):
            out = tmp_path / f"{tag}.{kind}"
            write(out, index=False)
            manifest = _manifest(tmp_path, tag, out, kind)
            sides.append(_old_shape(tmp_path / f"{tag}_{kind}.json", manifest))
        got = _data_level(*sides)
        assert got["change"] is False
        assert [d["row_count_a"] for d in got["deltas"]] == [2]
        entry = json.loads(sides[0].read_text(encoding="utf-8"))["output_fingerprints"]["t"]
        assert "format" not in entry
        assert runner.invoke(app, ["report", "verify", str(sides[0])]).exit_code == 0


def test_report_diff_old_manifest_pq_holds_csv(tmp_path: Path) -> None:
    paths = []
    for tag in ("a", "b"):
        out = tmp_path / f"{tag}.pq"
        _FRAME.to_csv(out, index=False)  # what the old CLI wrote for a .pq path
        manifest = _manifest(tmp_path, tag, out, "parquet")
        paths.append(_old_shape(tmp_path / f"{tag}.json", manifest))
    got = _data_level(*paths)
    assert got["change"] is False
    assert [d["row_count_a"] for d in got["deltas"]] == [2]


def test_report_diff_sides_read_independently(tmp_path: Path) -> None:
    ev_a, ev_b = tmp_path / "ev_a.json", tmp_path / "ev_b.json"
    _run_people(tmp_path / "a", _target("parquet", tmp_path / "a" / "a.pq"), ev_a)
    _run_people(tmp_path / "b", _target("csv", tmp_path / "b" / "b.csv"), ev_b)
    got = _data_level(ev_a, ev_b)
    assert got["change"] is False
    assert [(d["row_count_a"], d["row_count_b"]) for d in got["deltas"]] == [(3, 3)]


def test_unreadable_entries_are_value_free(tmp_path: Path) -> None:
    out = tmp_path / "out.csv"
    out.write_text(f"id,name\n{_CELL},{_CELL}\n", encoding="utf-8")
    base = _manifest(tmp_path, "a", out, "csv")
    bad = tmp_path / "bad.csv"
    bad.write_bytes(b"id,name\n\xff\xfe\x80,\xc3\x28\n")
    # A fixed-width file the engine refuses (a DecoyError, not a ValueError).
    refused = tmp_path / "refused.txt"
    refused.write_text(f"{_CELL}xyz\n", encoding="utf-8")
    refused_layout = {
        "columns": [
            {"name": "id", "start": 0, "width": 7},
            {"name": "n", "start": 7, "width": 3, "type": "int", "align": "right"},
        ]
    }
    cases = {
        "engine_refused_fixed_width": {
            "path": str(refused),
            "format": "fixed_width",
            "layout": refused_layout,
        },
        "layout_not_a_mapping": {"format": "fixed_width", "layout": 5},
        "layout_without_columns": {"format": "fixed_width", "layout": {"columns": 5}},
        "unknown_format": {"format": "xml"},
        "fixed_width_no_layout": {"format": "fixed_width"},
        "undecodable_csv": {"path": str(bad), "format": "csv"},
    }
    for label, entry in cases.items():
        ev = _write_manifest(tmp_path / f"{label}.json", base, **entry)
        soft = _diff(ev, ev)
        assert soft.exit_code == 0, (label, soft.output)
        assert json.loads(soft.stdout)["data_level"] == "skipped", label
        strict = _diff(ev, ev, "--require-data")
        assert strict.exit_code == EXIT_USAGE, (label, strict.output)
        for output in (soft.output, strict.output):
            assert _CELL not in output


# ---------------------------------------------------------------------------
# init and scan read Parquet through the one reader (characterization pin)
# ---------------------------------------------------------------------------

# Recorded on the base tree (A2 head 16e82b1), with the temp folder replaced by <TMP>.
_INIT_YAML_SHA256 = "bd50b329e465ee4209a490ee97982d05aecc2fa7d65fd3a9105048c123271c0c"
_SCAN_JSON_SHA256 = "81b904aa55af6552451bd44d1cbec86b3cf9f860f0d4aaa2f56df720f090a476"


def test_init_and_scan_parquet_unchanged(tmp_path: Path) -> None:
    src = tmp_path / "people.parquet"
    pd.DataFrame(
        {
            "email": [f"user{i}@example.com" for i in range(20)],
            "name": [f"Person {i}" for i in range(20)],
            "age": list(range(20, 40)),
        }
    ).to_parquet(src, index=False)
    out = tmp_path / "pipeline.yaml"
    init = runner.invoke(app, ["init", str(src), "--output", str(out), "--yes"])
    assert init.exit_code == 0, init.output
    scan = runner.invoke(app, ["scan", str(src), "--json"])
    assert scan.exit_code == 0, scan.output
    texts = (out.read_text(encoding="utf-8"), scan.stdout)
    digests = [
        hashlib.sha256(t.replace(str(tmp_path), "<TMP>").encode()).hexdigest() for t in texts
    ]
    assert digests == [_INIT_YAML_SHA256, _SCAN_JSON_SHA256]


@needs_vault
def test_unmask_of_a_file_in_the_wrong_format_fails_closed(tmp_path: Path) -> None:
    layout = _vault_layout(tmp_path)
    cfg, vault = _masked_vault_run(tmp_path, _target("fixed_width", tmp_path / "m.txt", layout))
    shutil.copy(tmp_path / "m.txt", tmp_path / "copy.dat")  # not the target: read as CSV
    result = _unmask(cfg, tmp_path / "copy.dat", vault, tmp_path / "rec.csv")
    assert result.exit_code == EXIT_USAGE, result.output
    assert "unmask_columns_missing" in result.output
    assert not (tmp_path / "rec.csv").exists()
    assert "REDACTED" not in result.output


@needs_vault
def test_unreadable_declaration_prints_its_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    masked = tmp_path / "m.dat"
    masked.write_text("id,email,name\nr0,a,b\n", encoding="utf-8")
    cfg = _vault_config(tmp_path, {"format": "xml", "path": str(masked)})
    result = runner.invoke(app, ["unmask", str(cfg), str(masked)])
    assert result.exit_code == EXIT_USAGE, result.output
    assert "target_format_unreadable" in result.output

    import decoy.cli.tokenize as tokenize_module
    from decoy.cli.io import TargetFormatError

    def refuse(*_a: object, **_k: object) -> None:
        raise TargetFormatError(
            "target_format_unreadable", "the file's format cannot be determined"
        )

    tcfg, vault = _tokenize(tmp_path / "tok", "tok.csv", "csv")
    monkeypatch.setattr(tokenize_module, "input_format", refuse)
    result = _detok(tcfg, tmp_path / "tok" / "tok.csv", vault)
    assert result.exit_code == EXIT_USAGE, result.output
    assert "target_format_unreadable" in result.output
