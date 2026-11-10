"""AT-P3: every private CLI surface is owner-only under umask 000 (X7c slice S2).

Each command runs in a child process that clears the umask first, so a file that is 0600
here got that mode from `_private_file`, not from the host's default umask.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

import pandas as pd
import pytest
import yaml

from tests.ci_support import MANIFEST_NAME, ci_manifest, make_repo, write, write_clean_pipeline
from tests.csv_sources import csv_source
from tests.keyed_secret import TEST_MASK_SECRET_REF, secret_env

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX file modes")

_BOOT = "import os, sys; os.umask(0); from decoy.__main__ import app; app()"
_EMAILS = ["a@x.com", "b@y.com", "a@x.com"]


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update({"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200", "PYTHONUTF8": "1"})
    env.update(secret_env())
    return env


def _decoy(cwd: Path, *argv: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        [sys.executable, "-c", _BOOT, *argv],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=_env(),
        timeout=300,
        check=False,
    )
    assert proc.returncode == expect, proc.stderr + proc.stdout
    return proc


def _config(
    root: Path, columns: list[dict], *, out: str = "out.csv", name: str = "pipeline.yaml"
) -> Path:
    src = root / "in.csv"
    pd.DataFrame({"id": range(len(_EMAILS)), "email": _EMAILS}).to_csv(src, index=False)
    cfg = {
        "version": 2,
        "global_settings": {"seed": 42, "mask_secret_ref": TEST_MASK_SECRET_REF},
        "sources": {"people": csv_source(src)},
        "tables": [{"name": "people", "columns": columns}],
        "targets": {"people": {"type": "file", "format": "csv", "path": str(root / out)}},
    }
    path = root / name
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


_HASH = [
    {"name": "id", "strategy": "passthrough"},
    {"name": "email", "strategy": "hash", "namespace": "email_ns"},
]
_TOKEN = [
    {"name": "id", "strategy": "passthrough"},
    {"name": "email", "strategy": "tokenize", "namespace": "people.email"},
]
_VAULTED = [
    {"name": "id", "strategy": "passthrough"},
    {"name": "email", "strategy": "hash", "namespace": "em", "vault": True},
]


def test_compile_output_is_private_and_its_bytes_are_the_rendered_plan(tmp_path: Path) -> None:
    from decoy_engine import __version__ as engine_version
    from decoy_engine.plan import compile_plan

    from decoy.cli.plan import empty_profile_for_no_profile, render_plan_artifact

    cfg = _config(tmp_path, _HASH)
    plan_path = tmp_path / "plan.yaml"
    _decoy(tmp_path, "validate", "compile", str(cfg), "--no-profile", "--output", str(plan_path))
    assert _mode(plan_path) == 0o600
    # The old writer was `Path.write_text(render_plan_artifact(...))`, so the golden is the
    # same render of the same config; only the writer changed.
    raw = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    plan = compile_plan(
        raw,
        empty_profile_for_no_profile(raw, engine_version),
        decoy_engine_version=engine_version,
        no_profile=True,
    )
    assert plan_path.read_bytes() == render_plan_artifact(plan, "yaml").encode("utf-8")


@pytest.mark.parametrize("as_json", [False, True])
def test_compile_output_write_failure_exits_3_with_the_code(tmp_path: Path, as_json: bool) -> None:
    cfg = _config(tmp_path, _HASH)
    plan_path = tmp_path / "plan.yaml"
    code = (
        "import os, sys\n"
        "real = os.replace\n"
        "def fail(src, dst, *a, **k):\n"
        "    if os.path.basename(os.fspath(dst)) == 'plan.yaml':\n"
        "        raise OSError(5, 'disk says no')\n"
        "    return real(src, dst, *a, **k)\n"
        "os.replace = fail\n" + _BOOT
    )
    argv = ["validate", "compile", str(cfg), "--no-profile", "--output", str(plan_path)]
    if as_json:
        argv.append("--json")
    proc = subprocess.run(
        [sys.executable, "-c", code, *argv],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env=_env(),
        timeout=300,
        check=False,
    )
    assert proc.returncode == 3, proc.stderr + proc.stdout
    assert "Traceback" not in proc.stderr + proc.stdout
    assert not plan_path.exists()
    if as_json:
        envelope = json.loads(proc.stdout)
        assert envelope["status"] == "error"
        assert "atomic_write_failed" in envelope["error"]
    else:
        assert "atomic_write_failed" in proc.stderr


def test_tokenize_vault_and_its_journal_are_private(tmp_path: Path) -> None:
    cfg = _config(tmp_path, _TOKEN)
    vault = tmp_path / "sub" / "tokens.db"
    _decoy(tmp_path, "tokenize", str(cfg), "--vault", str(vault))
    assert _mode(vault) == 0o600
    assert _mode(vault.parent) == 0o700
    # The journal exists only while a write transaction is open, so hold one in the child.
    code = textwrap.dedent(
        """
        import os, stat, sys
        os.umask(0)
        from pathlib import Path
        from decoy.cli._token_vault import LocalTokenVault
        path = Path(sys.argv[1])
        with LocalTokenVault(path, create=True) as v:
            v.put("ns", "plain", "tok_1")
            journal = Path(str(path) + "-journal")
            print(stat.S_IMODE(journal.stat().st_mode), journal.exists())
            v.commit()
        """
    )
    proc = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path / "held.db")],
        capture_output=True,
        text=True,
        check=True,
    )
    mode, exists = proc.stdout.split()
    assert exists == "True" and int(mode) == 0o600


def test_unmask_and_detokenize_outputs_are_private(tmp_path: Path) -> None:
    cfg = _config(tmp_path, _HASH)
    _decoy(tmp_path, "run", str(cfg))
    unmasked = tmp_path / "unmasked.csv"
    _decoy(tmp_path, "unmask", str(cfg), str(tmp_path / "out.csv"), "-o", str(unmasked))
    assert _mode(unmasked) == 0o600

    tok = tmp_path / "tok"
    tok.mkdir()
    tcfg = _config(tok, _TOKEN, out="tokenized.csv")
    vault = tok / "tokens.db"
    _decoy(tok, "tokenize", str(tcfg), "--vault", str(vault))
    _decoy(tok, "detokenize", str(tcfg), str(tok / "tokenized.csv"), "--vault", str(vault))
    assert _mode(tok / "tokenized.detokenized.csv") == 0o600


def test_run_vault_and_evidence_are_private(tmp_path: Path) -> None:
    pytest.importorskip("cryptography")
    cfg = _config(tmp_path, _VAULTED)
    vault, evidence = tmp_path / "vault.bin", tmp_path / "evidence.json"
    _decoy(tmp_path, "run", str(cfg), "--vault", str(vault), "--evidence-out", str(evidence))
    assert _mode(vault) == 0o600
    assert _mode(evidence) == 0o600


def test_setup_settings_file_is_private(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "decoy-home"
    monkeypatch.setenv("DECOY_HOME", str(home))
    _decoy(tmp_path, "setup", "--yes")
    assert _mode(home / "settings.json") == 0o600


def test_fit_and_scan_outputs_are_private(tmp_path: Path) -> None:
    src = tmp_path / "source.csv"
    pd.DataFrame({"amount": [10.5, 22.1, 9.9] * 20, "state": ["CA", "NY", "TX"] * 20}).to_csv(
        src, index=False
    )
    snapshot, scan_out = tmp_path / "snapshot.json", tmp_path / "scan.json"
    _decoy(tmp_path, "fit", str(src), "-o", str(snapshot))
    _decoy(tmp_path, "scan", str(src), "-o", str(scan_out))
    assert _mode(snapshot) == 0o600
    assert _mode(scan_out) == 0o600


def test_report_writers_are_private(tmp_path: Path) -> None:
    cfg = _config(tmp_path, _HASH)
    evidence = tmp_path / "evidence.json"
    _decoy(tmp_path, "run", str(cfg), "--evidence-out", str(evidence))
    rendered, shown = tmp_path / "report.html", tmp_path / "report.md"
    # `_render` (report render) and `_write_out` (report show) are the two writing functions.
    _decoy(tmp_path, "report", "render", str(evidence), "-o", str(rendered))
    _decoy(tmp_path, "report", "show", str(evidence), "--format", "markdown", "-o", str(shown))
    assert _mode(rendered) == 0o600
    assert _mode(shown) == 0o600


def test_ci_report_and_debug_log_are_private(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    write_clean_pipeline(repo)
    write(repo, MANIFEST_NAME, ci_manifest())
    _decoy(
        repo,
        "ci",
        "check",
        MANIFEST_NAME,
        "--format",
        "json",
        "--output",
        "report.json",
        "--unsafe-debug-log",
        "debug.log",
    )
    assert json.loads((repo / "report.json").read_text(encoding="utf-8"))
    assert _mode(repo / "report.json") == 0o600
    assert _mode(repo / "debug.log") == 0o600


def test_mask_spool_is_private_while_it_exists(tmp_path: Path) -> None:
    cfg = _config(tmp_path, _HASH)
    code = textwrap.dedent(
        """
        import os, stat, sys
        os.umask(0)
        import pandas as pd
        import pyarrow.parquet as pq
        import decoy

        seen = []
        real = pq.write_table

        def spy(table, where, *a, **k):
            seen.append(stat.S_IMODE(os.stat(where).st_mode))
            return real(table, where, *a, **k)

        pq.write_table = spy
        frame = pd.DataFrame({"id": [0, 1], "email": ["a@x.com", "b@y.com"]})
        decoy.mask(frame, sys.argv[1])
        print(seen[0])
        """
    )
    proc = subprocess.run(
        [sys.executable, "-c", code, str(cfg)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env=_env(),
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert int(proc.stdout.split()[-1]) == 0o600
