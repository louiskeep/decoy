"""Seeded-secret contract: pre-scan / post-scan never emit raw values.

Distinctive secrets are planted in cell values (including the positions that
become top values and sentinels), file paths, rejected option values and engine
exception messages. Every ordinary output surface (stdout, stderr, JSON,
verbose logs, error paths) is then scanned for them. The only surface allowed
to carry values is the saved profile file the user explicitly asks for with
`pre-scan --output FILE`; nothing in this file inspects that artifact.
"""

from __future__ import annotations

import json as _json
import logging
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from decoy.__main__ import app

runner = CliRunner()

CELL = "ZQXCELL7431"  # repeated, so it becomes the top value / mode
MISS = "ZQXMISS5528"  # detector miss sample
SENT = "ZQXSENT9917"  # repeated sentinel-like token
PATHSEC = "ZQXPATH2290"
OPTSEC = "ZQXOPT6604"
EXCSEC = "ZQXEXC8813"
ALL_SECRETS = (CELL, MISS, SENT, PATHSEC, OPTSEC, EXCSEC)


def _surfaces(result) -> str:
    parts = [result.stdout or "", result.stderr or "", result.output or ""]
    if result.exception is not None and not isinstance(result.exception, SystemExit):
        parts.append(f"UNCAUGHT {type(result.exception).__name__}: {result.exception}")
    return "\n".join(parts)


def _assert_clean(result, caplog=None, extra: str = "") -> None:
    text = _surfaces(result) + extra
    if caplog is not None:
        text += "\n".join(r.getMessage() for r in caplog.records)
    for secret in ALL_SECRETS:
        assert secret not in text, f"{secret} leaked:\n{text}"
    assert "Traceback" not in text, text
    assert not (
        result.exception is not None and not isinstance(result.exception, SystemExit)
    ), "uncaught exception"


@pytest.fixture
def work(tmp_path: Path) -> Path:
    d = tmp_path / f"dir_{PATHSEC}"
    d.mkdir()
    return d


@pytest.fixture
def source(work: Path) -> Path:
    p = work / f"src_{PATHSEC}.csv"
    pd.DataFrame(
        {
            "email": [CELL] * 6 + [MISS, "a@x.com", "b@x.com", "c@x.com"],
            "code": [SENT] * 5 + ["ok"] * 5,
            "n": [-99999, -99999, 1, 2, 3, 4, 5, 6, 7, 8],
        }
    ).to_csv(p, index=False)
    return p


@pytest.fixture
def masked(work: Path, source: Path) -> Path:
    p = work / f"masked_{PATHSEC}.csv"
    p.write_text(source.read_text())
    return p


@pytest.fixture
def boom_profile(monkeypatch):
    import decoy_engine

    def boom(*a, **k):
        raise ValueError(f"bad row {CELL} {EXCSEC}")

    monkeypatch.setattr(decoy_engine, "profile_columns", boom)


PRE_OK = [
    [],
    ["--json"],
    ["--json", "--show-fields"],
    ["--show-fields"],
    ["-v"],
    ["-q"],
    ["--output", "-"],
    ["--output", "-", "--json"],
    ["--output", "-", "-q"],
    ["--rows", "5", "--strategy", "head"],
]


@pytest.mark.parametrize("flags", PRE_OK, ids=[" ".join(f) or "plain" for f in PRE_OK])
def test_pre_scan_success_surfaces_value_free(source, flags, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    r = runner.invoke(app, ["pre-scan", str(source), *flags])
    _assert_clean(r, caplog)


def test_pre_scan_output_dash_is_value_free_projection(source) -> None:
    r = runner.invoke(app, ["pre-scan", str(source), "--output", "-"])
    assert r.exit_code == 0, r.output
    payload = _json.loads(r.stdout)
    assert payload["row_count"] == 10
    for f in payload["fields"]:
        for banned in ("top_values", "sentinels", "min_value", "max_value", "mode_value",
                       "distribution", "sample_invalid", "detector_matches"):
            assert banned not in f
    assert "source_label" not in payload


@pytest.mark.parametrize("flags", [[], ["--json"], ["-v"], ["--output", "-"]])
def test_pre_scan_crash_path_value_free(source, boom_profile, flags, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    r = runner.invoke(app, ["pre-scan", str(source), *flags])
    assert r.exit_code == 3
    _assert_clean(r, caplog)
    assert "ValueError" in _surfaces(r)


def test_pre_scan_saved_file_then_fields_show_diff_value_free(source, work) -> None:
    saved = work / f"scan_{PATHSEC}.json"
    r = runner.invoke(app, ["pre-scan", str(source), "--output", str(saved)])
    assert r.exit_code == 0, r.output
    _assert_clean(r)
    # The saved file is the one explicit artifact allowed to hold values.
    assert CELL in saved.read_text()
    for argv in (
        ["pre-scan", "fields", str(saved)],
        ["pre-scan", "fields", str(saved), "--json"],
        ["pre-scan", "show", str(saved), "email"],
        ["pre-scan", "show", str(saved), "email", "--json"],
        ["pre-scan", "show", str(saved), f"no_{OPTSEC}"],
        ["pre-scan", "show", str(saved), f"no_{OPTSEC}", "--json"],
        ["pre-scan", "diff", str(saved), str(saved)],
        ["pre-scan", "diff", str(saved), str(saved), "--json"],
        ["pre-scan", "fields", str(work / f"missing_{PATHSEC}.json")],
        ["pre-scan", "fields", str(work / f"missing_{PATHSEC}.json"), "--json"],
    ):
        r = runner.invoke(app, argv)
        _assert_clean(r)


def test_pre_scan_load_errors_value_free(work) -> None:
    bad = work / f"bad_{PATHSEC}.json"
    bad.write_text(f'{{"fields": [{EXCSEC}')
    notutf = work / f"nu_{PATHSEC}.json"
    notutf.write_bytes(b"\xff\xfe" + EXCSEC.encode())
    for p in (bad, notutf):
        for extra in ([], ["--json"]):
            _assert_clean(runner.invoke(app, ["pre-scan", "fields", str(p), *extra]))
            _assert_clean(runner.invoke(app, ["pre-scan", "show", str(p), "x", *extra]))
            _assert_clean(runner.invoke(app, ["pre-scan", "diff", str(p), str(p), *extra]))


def test_pre_scan_usage_errors_value_free(source, work) -> None:
    layout = work / f"layout_{PATHSEC}.yaml"
    layout.write_text(f"[unclosed {EXCSEC}")
    cases = [
        ["--strategy", OPTSEC],
        ["--format", OPTSEC],
        ["--rows", OPTSEC],
        ["--format", "fixed-width"],
        ["--format", "fixed-width", "--layout", str(layout)],
        ["--format", "fixed-width", "--layout", str(work / f"nolayout_{PATHSEC}.yaml")],
        ["--layout", str(work / f"nolayout_{PATHSEC}.yaml"), "--format", "fixed-width"],
        [f"--bogus-{OPTSEC}"],
    ]
    for flags in cases:
        for mode in ([], ["--json"], ["-v"]):
            r = runner.invoke(app, ["pre-scan", str(source), *flags, *mode])
            assert r.exit_code != 0
            _assert_clean(r)
    r = runner.invoke(app, ["pre-scan", str(work / f"nope_{PATHSEC}.csv")])
    assert r.exit_code != 0
    _assert_clean(r)
    r = runner.invoke(app, ["pre-scan", str(source), "--json", "--output", "-"])
    assert r.exit_code != 0
    _assert_clean(r)


MODES = [[], ["--json"], ["-v"], ["-q"]]


@pytest.mark.parametrize("mode", MODES, ids=["text", "json", "verbose", "quiet"])
def test_post_scan_integrity_success_and_files(source, masked, work, mode, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    rep = work / f"rep_{PATHSEC}.json"
    r = runner.invoke(
        app,
        ["post-scan", "integrity", str(masked), "--source", str(source),
         "--output", str(rep), *mode],
    )
    assert r.exit_code in (0, 4), r.output
    _assert_clean(r, caplog, extra=rep.read_text() if rep.exists() else "")


@pytest.mark.parametrize("mode", MODES, ids=["text", "json", "verbose", "quiet"])
def test_post_scan_integrity_error_and_crash_paths(source, masked, work, mode, monkeypatch) -> None:
    cfg = work / f"cfg_{PATHSEC}.yaml"
    cfg.write_text(f"{OPTSEC}: [{EXCSEC}\n")
    cfg2 = work / f"cfg2_{PATHSEC}.yaml"
    cfg2.write_text(f"{OPTSEC}: {EXCSEC}\nversion: 2\n")
    for argv in (
        ["post-scan", "integrity", str(masked), "--source", str(work / f"no_{PATHSEC}.csv")],
        ["post-scan", "integrity", str(work / f"no_{PATHSEC}.csv"), "--source", str(source)],
        ["post-scan", "integrity", str(masked), "--source", str(source), "--config", str(cfg)],
        ["post-scan", "integrity", str(masked), "--source", str(source), "--config", str(cfg2)],
    ):
        r = runner.invoke(app, [*argv, *mode])
        assert r.exit_code != 0
        _assert_clean(r)

    import decoy_engine.verification as ver

    def boom(*a, **k):
        raise RuntimeError(f"row {CELL} {EXCSEC}")

    monkeypatch.setattr(ver, "run_post_mask", boom)
    r = runner.invoke(app, ["post-scan", "integrity", str(masked), "--source", str(source), *mode])
    assert r.exit_code == 3
    _assert_clean(r)


def test_post_scan_integrity_source_mismatch_warning_value_free(source, masked, work) -> None:
    cfg = work / f"cfg_{PATHSEC}.yaml"
    cfg.write_text(
        "version: 2\nsources:\n  t:\n    path: " + str(work / f"other_{PATHSEC}.csv")
        + "\ntables:\n  - name: t\n    source: t\n"
    )
    r = runner.invoke(
        app, ["post-scan", "integrity", str(masked), "--source", str(source), "--config", str(cfg)]
    )
    _assert_clean(r)


@pytest.mark.parametrize("mode", MODES, ids=["text", "json", "verbose", "quiet"])
def test_post_scan_fidelity_surfaces_value_free(source, masked, work, mode, monkeypatch) -> None:
    rep = work / f"fid_{PATHSEC}.json"
    r = runner.invoke(
        app, ["post-scan", "fidelity", str(source), str(masked), "--report-out", str(rep), *mode]
    )
    assert r.exit_code in (0, 4), r.output
    _assert_clean(r, extra=rep.read_text() if rep.exists() else "")

    bad_cfg = work / f"pc_{PATHSEC}.yaml"
    bad_cfg.write_text(f"{OPTSEC}: [{EXCSEC}\n")
    bad_cfg2 = work / f"pc2_{PATHSEC}.yaml"
    bad_cfg2.write_text(f"{OPTSEC}: {EXCSEC}\n")
    pol_list = work / f"pol_{PATHSEC}.yaml"
    pol_list.write_text(f"- {EXCSEC}\n")
    base = ["post-scan", "fidelity", str(source), str(masked)]
    for extra in (
        ["--joint", OPTSEC],
        ["--joint", f"{OPTSEC},{CELL},{EXCSEC}"],
        ["--min-grade", OPTSEC],
        ["--min-grade", "A", "--min-score", "0.5"],
        ["--mode", OPTSEC],
        ["--min-score", OPTSEC],
        ["--config", str(bad_cfg)],
        ["--config", str(bad_cfg2)],
        ["--policy", str(bad_cfg)],
        ["--policy", str(pol_list)],
    ):
        r = runner.invoke(app, [*base, *extra, *mode])
        assert r.exit_code != 0, extra
        _assert_clean(r)
    for argv in (
        ["post-scan", "fidelity", str(work / f"no_{PATHSEC}.csv"), str(masked), *mode],
        ["post-scan", "fidelity", str(source), str(work / f"no_{PATHSEC}.csv"), *mode],
    ):
        r = runner.invoke(app, argv)
        assert r.exit_code != 0
        _assert_clean(r)

    import decoy_engine.quality as q

    def boom(*a, **k):
        raise RuntimeError(f"row {CELL} {EXCSEC}")

    monkeypatch.setattr(q, "compute_quality_report", boom)
    r = runner.invoke(app, [*base, *mode])
    assert r.exit_code == 3
    _assert_clean(r)


def test_post_scan_fidelity_unreadable_csv_value_free(source, work, monkeypatch) -> None:
    junk = work / f"junk_{PATHSEC}.csv"
    junk.write_bytes(b"\xff\xfe\x00" + EXCSEC.encode() * 3)
    r = runner.invoke(app, ["post-scan", "fidelity", str(source), str(junk), "--json"])
    assert r.exit_code != 0
    _assert_clean(r)
