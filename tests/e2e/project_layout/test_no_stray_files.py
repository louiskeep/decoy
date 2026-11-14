"""AT-12 and AT-13: no command leaves a file where the guarantee does not allow one.

Each command runs as a real process with default flags, the current folder outside the project
and `$HOME` pointed at a scratch folder. Before and after each command the test lists every path
under the project, the current folder, the home stand-in and the input folder, and requires each
new path to sit under the places that command may write: its run folder, a path typed on its
command line, the folder of an input it was given, or the demo folder. A canary value in the
source must never appear on stdout, stderr or in `--json`, on success or on any refusal.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

CANARY_EMAIL = "zq9canary@canary-host.test"
CANARY_SSN = "731-55-9042"
SECRET = "cd" * 32


def _pipeline(source: Path, columns: list[dict], target: str) -> str:
    cfg = {
        "version": 2,
        "global_settings": {"seed": 7, "mask_secret_ref": "env:DECOY_STRAY_SECRET"},
        "sources": {
            "t": {"type": "file", "format": "csv", "path": str(source), "has_header": True}
        },
        "tables": [{"name": "t", "columns": columns}],
        "targets": {"t": {"type": "file", "format": "csv", "path": target}},
    }
    return yaml.safe_dump(cfg)


FPE = {
    "name": "ssn",
    "strategy": "fpe",
    "namespace": "ssn_identity",
    "provider_config": {"charset": "digits"},
}
HASH = {"name": "email", "strategy": "hash", "namespace": "email_identity"}
TOKENIZE = {"name": "email", "strategy": "tokenize", "namespace": "people.email"}


class World:
    """A project, a source folder, an unrelated current folder and a home stand-in."""

    def __init__(self, base: Path) -> None:
        self.home = base / "home"
        self.cwd = base / "cwd"
        self.data = base / "data"
        self.typed = base / "typed"
        self.project = base / "proj"
        for folder in (self.home, self.cwd, self.data, self.typed, self.project / "pipelines"):
            folder.mkdir(parents=True)
        (self.project / "decoy.yaml").write_text("kind: decoy-project/v1\n", encoding="utf-8")
        self.source = self.data / "people.csv"
        pd.DataFrame(
            {
                "ssn": [CANARY_SSN, "612-33-7781", "455-90-1208"],
                "email": [CANARY_EMAIL, "b@x.test", "c@x.test"],
            }
        ).to_csv(self.source, index=False)
        self.roots = (self.project, self.cwd, self.home, self.data, self.typed)
        self.env = {
            **os.environ,
            "HOME": str(self.home),
            "USERPROFILE": str(self.home),
            "DECOY_STRAY_SECRET": SECRET,
            "NO_COLOR": "1",
            "COLUMNS": "400",
        }
        for key in ("DECOY_PROJECT", "DECOY_MASTER_KEY", "CI"):
            self.env.pop(key, None)

    def pipeline(self, name: str, columns: list[dict], target: str = "out.csv") -> None:
        folder = self.project / "pipelines" / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "pipeline.yaml").write_text(
            _pipeline(self.source, columns, target), encoding="utf-8"
        )

    def snapshot(self) -> set[Path]:
        return {p for root in self.roots for p in root.rglob("*")}

    def run(self, *args: str) -> tuple[subprocess.CompletedProcess[str], set[Path]]:
        before = self.snapshot()
        done = subprocess.run(
            [sys.executable, "-m", "decoy", "--project", str(self.project), *args],
            cwd=self.cwd,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        return done, self.snapshot() - before

    def run_dir(self, name: str) -> Path:
        (run,) = [
            p for p in (self.project / "out" / name).iterdir() if p.is_dir() and not p.is_symlink()
        ]
        return run


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path)


def _under(path: Path, *roots: Path) -> bool:
    return any(path == root or root in path.parents for root in roots)


def _assert_quiet(done: subprocess.CompletedProcess[str]) -> None:
    """Neither stream carries a canary value or any piece of one."""
    text = done.stdout + done.stderr
    for needle in (CANARY_EMAIL, CANARY_SSN, "zq9canary", "canary-host", "731-55"):
        assert needle not in text, f"{needle!r} reached the output"


def _assert_only(step: str, new: set[Path], *allowed: Path) -> None:
    stray = sorted(str(p) for p in new if not _under(p, *allowed))
    assert not stray, f"{step} wrote outside its places: {stray}"
    assert not [p for p in new if p.name == "logs"], f"{step} made a logs folder"


def test_each_command_writes_only_where_the_guarantee_allows(world: World) -> None:
    w = world
    w.pipeline("mask", [FPE, HASH])
    w.pipeline("tok", [{"name": "ssn", "strategy": "passthrough"}, TOKENIZE], "tok.csv")

    done, new = w.run("project", "new", str(w.cwd / "fresh"))
    assert done.returncode == 0, done.stderr
    _assert_only("project new", new, w.cwd / "fresh")

    done, new = w.run("init", "initd", "--source", str(w.source))
    assert done.returncode == 0, done.stderr
    _assert_only("init", new, w.project / "pipelines" / "initd")

    done, new = w.run("scan", str(w.source), "--has-header")
    assert done.returncode == 0, done.stderr
    _assert_quiet(done)
    _assert_only("scan", new)

    done, new = w.run("validate", "mask")
    assert done.returncode == 0, done.stdout + done.stderr
    _assert_quiet(done)
    _assert_only("validate", new)

    done, new = w.run("run", "mask", "--json")
    assert done.returncode == 0, done.stdout + done.stderr
    _assert_quiet(done)
    run = w.run_dir("mask")
    _assert_only("run", new, w.project / "out")
    assert json.loads(done.stdout)["output_dir"] == str(run)
    masked = run / "out.csv"

    done, new = w.run("unmask", "mask", str(masked))
    assert done.returncode == 0, done.stdout + done.stderr
    _assert_quiet(done)
    _assert_only("unmask", new, run)

    done, new = w.run("report", "fidelity", str(w.source), str(masked), "--config", "mask")
    assert done.returncode in (0, 4), done.stdout + done.stderr
    _assert_quiet(done)
    _assert_only("report fidelity", new, run / "reports")

    done, new = w.run(
        "report", "integrity", str(masked), "--source", str(w.source), "--config", "mask"
    )
    assert done.returncode in (0, 4), done.stdout + done.stderr
    _assert_quiet(done)
    _assert_only("report integrity", new, run / "reports")

    vault = w.typed / "tokens.db"
    done, new = w.run("tokenize", "tok", "--vault", str(vault))
    assert done.returncode == 0, done.stdout + done.stderr
    _assert_quiet(done)
    tok_run = w.run_dir("tok")
    # The vault's lock file stays beside the typed vault path.
    _assert_only("tokenize", new, w.project / "out", vault, vault.with_name(f".{vault.name}.lock"))

    done, new = w.run("detokenize", "tok", str(tok_run / "tok.csv"), "--vault", str(vault))
    assert done.returncode == 0, done.stdout + done.stderr
    _assert_quiet(done)
    _assert_only("detokenize", new, tok_run)

    done, new = w.run("fit", str(w.source))
    assert done.returncode == 0, done.stdout + done.stderr
    _assert_quiet(done)
    _assert_only("fit", new, w.data)

    done, new = w.run("demo")
    assert done.returncode == 0, done.stdout + done.stderr
    _assert_only("demo", new, w.cwd / "decoy_demo")

    done, new = w.run("run", "--all")
    assert done.returncode in (0, 1, 3), done.stdout + done.stderr
    _assert_quiet(done)
    _assert_only("run --all", new, w.project / "out")

    assert not [p for p in w.snapshot() if p.name == "logs"]
    assert not list(w.home.rglob("*")), "a command wrote into the home folder"


def test_refusals_write_nothing_and_name_no_value(world: World) -> None:
    w = world
    w.pipeline("escape", [HASH], "../../escape.csv")
    w.pipeline("broken", [HASH], "out.csv")
    (w.project / "pipelines" / "broken" / "pipeline.yaml").write_text(
        "version: 2\nsources: [\n" + CANARY_EMAIL, encoding="utf-8"
    )
    for step, args in (
        ("escape run", ("run", "escape")),
        ("escape validate", ("validate", "escape")),
        ("unparsable run", ("run", "broken")),
        ("unknown name", ("run", "no-such-pipeline")),
        ("bad name", ("run", "../x")),
        ("bad out-dir", ("run", "escape", "--out-dir", "../../elsewhere")),
    ):
        done, new = w.run(*args)
        assert done.returncode != 0, f"{step} should refuse"
        _assert_quiet(done)
        _assert_only(step, new, w.project / "out")
        assert not (w.project.parent / "escape.csv").exists()

    done, new = w.run("run", "escape", "--json")
    assert done.returncode != 0
    _assert_quiet(done)


def test_engine_opens_no_log_file_and_console_logging_still_prints(tmp_path: Path) -> None:
    """AT-13: the engine's default log file is off, and an opt-in console handler still writes."""
    probe = (
        "from decoy_engine.internal.logging import get_logger\n"
        "get_logger({'console': True}).warning('engine-advisory')\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert "engine-advisory" in done.stderr + done.stdout
    assert list(tmp_path.iterdir()) == []
