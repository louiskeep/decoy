"""AT-26: the plan's user walk-through as one test.

Two clients, two pipelines each, driven through the real CLI in one `$HOME` stand-in. Every
printed path is asserted and so is the final tree of the whole home folder. Time and the
invocation id are seeded for the in-process commands, so their run ids are exact. `run --all`
starts real child processes whose ids cannot be seeded; their run folders are checked for shape
and then written as `<RUN>` in the tree. Report numbers are not asserted: this test is about
where files go and which exit codes come back.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_FINDINGS, EXIT_OK, EXIT_USAGE
from decoy.cli.io import _layout
from decoy.cli.run import _flow

runner = CliRunner()
WIDE = {"COLUMNS": "1000"}
RUN_ID = re.compile(r"\d{8}T\d{12}Z-[0-9a-f]{8}")
SECRET = "ab" * 32
KEY = "env:DECOY_MASK_SECRET"


class _Seed:
    """The n-th run gets invocation id `0000000n-...` and starts n seconds after the base."""

    def __init__(self) -> None:
        self.count = 0

    def invocation_id(self) -> str:
        self.count += 1
        return f"{self.count:08x}-0000-4000-8000-000000000000"

    def now(self) -> datetime:
        return datetime(2026, 11, 9, 14, 15, 0, 1, tzinfo=timezone.utc) + timedelta(
            seconds=self.count
        )

    @staticmethod
    def run_id(n: int) -> str:
        return f"20261109T1415{n:02d}000001Z-{n:08x}"


@pytest.fixture
def seed(monkeypatch: pytest.MonkeyPatch) -> _Seed:
    seeded = _Seed()

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[no-untyped-def]
            return seeded.now()

    monkeypatch.setattr(_flow, "mint_invocation_id", seeded.invocation_id)
    monkeypatch.setattr(_layout, "datetime", Clock)
    return seeded


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "home"
    for sub in ("data/acme", "data/globex", "work"):
        (folder / sub).mkdir(parents=True)
    monkeypatch.setenv("HOME", str(folder))
    monkeypatch.setenv("USERPROFILE", str(folder))
    monkeypatch.setenv("DECOY_MASK_SECRET", SECRET)
    monkeypatch.delenv("DECOY_PROJECT", raising=False)
    monkeypatch.delenv("DECOY_MASTER_KEY", raising=False)
    for rel in ("acme/members.csv", "globex/claims.csv", "globex/providers.csv"):
        pd.DataFrame({"city": ["Austin", "Boston", "Denver"], "note": ["a", "b", "c"]}).to_csv(
            folder / "data" / rel, index=False
        )
    return folder


def _decoy(*args: str, input: str | None = None):
    return runner.invoke(app, list(args), env=WIDE, input=input)


def _json(result) -> dict:  # type: ignore[no-untyped-def]
    return json.loads(result.stdout)


def _tree(home: Path, seeded: tuple[str, ...] = ()) -> list[str]:
    """Every entry under home, unseeded run ids written as `<RUN>`, links shown with target."""
    lines = []
    for path in sorted(home.rglob("*")):
        rel = path.relative_to(home).as_posix()
        if path.is_symlink():
            rel += f" -> {path.readlink().as_posix()}"
        elif path.is_dir():
            rel += "/"
        lines.append(RUN_ID.sub(lambda m: m.group() if m.group() in seeded else "<RUN>", rel))
    return sorted(lines)


def _project_entries(name: str, pipelines: tuple[str, ...]) -> list[str]:
    base = f"work/{name}"
    lines = [
        f"{base}/",
        f"{base}/.decoy/",
        f"{base}/.decoy/.gitignore",
        f"{base}/decoy.yaml",
        f"{base}/out/",
        f"{base}/out/.gitignore",
        f"{base}/pipelines/",
    ]
    for pipeline in pipelines:
        lines += [f"{base}/pipelines/{pipeline}/", f"{base}/pipelines/{pipeline}/pipeline.yaml"]
    return lines


def _pipeline_out(
    project: str, name: str, runs: dict[str, tuple[str, ...]], latest: str
) -> list[str]:
    """`out/<name>/` with its run folders (each with its files), claim, pointer and link."""
    base = f"work/{project}/out/{name}"
    lines = [f"{base}/", f"{base}/LATEST", f"{base}/PIPELINE", f"{base}/current -> {latest}"]
    for run_id, files in runs.items():
        lines.append(f"{base}/{run_id}/")
        lines += [f"{base}/{run_id}/{f}" for f in files]
    return lines


def test_walkthrough(home: Path, seed: _Seed, monkeypatch: pytest.MonkeyPatch) -> None:
    work = home / "work"
    acme, globex = work / "acme", work / "globex"
    monkeypatch.chdir(work)

    # Two projects.
    for root in (acme, globex):
        made = _decoy("project", "new", root.name)
        assert made.exit_code == EXIT_OK, made.output
        assert str(root) in made.stdout
        assert (root / "decoy.yaml").read_text(encoding="utf-8") == "kind: decoy-project/v1\n"
        assert (root / "pipelines").is_dir()
        assert (root / "out" / ".gitignore").read_text(encoding="utf-8") == "*\n"

    # acme: one masking pipeline, one generate pipeline.
    monkeypatch.chdir(acme)
    source = home / "data" / "acme" / "members.csv"
    made = _decoy("init", "members-mask", "--source", str(source))
    assert made.exit_code == EXIT_OK, made.output
    made = _decoy("init", "members-generate", "--preset", "generate", input="\n" * 12)
    assert made.exit_code == EXIT_OK, made.output
    for name in ("members-mask", "members-generate"):
        assert (acme / "pipelines" / name / "pipeline.yaml").is_file()

    # A masking run from the project root, by name.
    first, second, third = (seed.run_id(n) for n in (1, 2, 3))
    ran = _decoy("run", "members-mask", "--mask-secret", KEY, "--json")
    assert ran.exit_code == EXIT_OK, ran.output
    payload = _json(ran)
    mask_run = acme / "out" / "members-mask" / first
    assert payload["output_dir"] == str(mask_run)
    assert payload["outputs"] == [{"table": "data", "path": str(mask_run / "members.masked.csv")}]
    assert payload["pipeline"]["name"] == "members-mask"
    assert payload["project"]["root"] == str(acme)

    # A generate run from inside another pipeline's folder.
    monkeypatch.chdir(acme / "pipelines" / "members-generate")
    ran = _decoy("run", "members-generate", "--json")
    assert ran.exit_code == EXIT_OK, ran.output
    generate_run = acme / "out" / "members-generate" / second
    assert _json(ran)["output_dir"] == str(generate_run)

    # The project overview names both last clean runs.
    monkeypatch.chdir(acme)
    shown = _json(_decoy("project", "show", "--json"))
    assert shown["root"] == str(acme)
    rows = {row["name"]: row for row in shown["pipelines"]}
    assert rows["members-mask"]["last_clean_run"] == first
    assert rows["members-generate"]["last_clean_run"] == second
    assert rows["members-mask"]["yaml"] == "pipelines/members-mask/pipeline.yaml"

    # A report on a file reached through the `current` link prints the real run folder.
    through_link = "out/members-mask/current/members.masked.csv"
    report = _decoy(
        "report", "integrity", through_link, "--source", str(source), "--config", "members-mask"
    )
    assert report.exit_code in (EXIT_OK, EXIT_FINDINGS), report.output
    assert f"Report: {mask_run / 'reports' / 'integrity.json'}" in report.stdout

    # globex: two pipelines, run together from outside the project.
    monkeypatch.chdir(globex)
    stems = {"claims-mask": "claims", "providers-mask": "providers"}
    for name, stem in stems.items():
        made = _decoy("init", name, "--source", str(home / "data" / "globex" / f"{stem}.csv"))
        assert made.exit_code == EXIT_OK, made.output
    monkeypatch.chdir(work)
    ran = _decoy("--project", "globex", "run", "--all", "--mask-secret", KEY)
    assert ran.exit_code == EXIT_OK, ran.output
    assert "All 2 pipelines exited 0." in ran.stdout
    for name, stem in stems.items():
        (child,) = [p for p in (globex / "out" / name).iterdir() if RUN_ID.fullmatch(p.name)]
        assert (child / f"{stem}.masked.csv").is_file()

    # A name outside any project is refused, and nothing is written for it.
    before = _tree(home)
    refused = _decoy("run", "claims-mask")
    assert refused.exit_code == EXIT_USAGE, refused.output
    assert "No Decoy project found" in refused.output
    assert _tree(home) == before

    # The projects one level down.
    listed = _json(_decoy("project", "list", "--json"))
    assert [(p["folder"], p["root"], p["pipelines"]) for p in listed["projects"]] == [
        ("acme", str(acme), 2),
        ("globex", str(globex), 2),
    ]

    # A second masking run: a new folder, and `LATEST` and `current` move to it.
    ran = _decoy("--project", "acme", "run", "members-mask", "--mask-secret", KEY, "--json")
    assert ran.exit_code == EXIT_OK, ran.output
    pipeline_out = acme / "out" / "members-mask"
    assert _json(ran)["output_dir"] == str(pipeline_out / third)
    assert (pipeline_out / "LATEST").read_text(encoding="utf-8").strip() == third
    assert (pipeline_out / "current").readlink().as_posix() == third
    assert (pipeline_out / "PIPELINE").read_text(encoding="utf-8") == (
        "pipelines/members-mask/pipeline.yaml\n"
    )

    # Fidelity through the link names the run `current` points at.
    fidelity = _decoy(
        "--project",
        "acme",
        "report",
        "fidelity",
        str(source),
        "acme/out/members-mask/current/members.masked.csv",
        "--config",
        "members-mask",
    )
    assert fidelity.exit_code in (EXIT_OK, EXIT_FINDINGS), fidelity.output
    assert f"Report: {pipeline_out / third / 'reports' / 'fidelity.json'}" in fidelity.stdout

    # The whole home folder, entry for entry: nothing beside a YAML, in `work`, or in `logs/`.
    expected = ["data/", "data/acme/", "data/acme/members.csv", "data/globex/"]
    expected += ["data/globex/claims.csv", "data/globex/providers.csv", "work/"]
    expected += _project_entries("acme", ("members-generate", "members-mask"))
    expected += _pipeline_out("acme", "members-generate", {second: ("employees.csv",)}, second)
    expected += _pipeline_out(
        "acme",
        "members-mask",
        {
            first: ("members.masked.csv", "reports/", "reports/integrity.json"),
            third: ("members.masked.csv", "reports/", "reports/fidelity.json"),
        },
        third,
    )
    expected += _project_entries("globex", tuple(stems))
    for name, stem in stems.items():
        expected += _pipeline_out("globex", name, {"<RUN>": (f"{stem}.masked.csv",)}, "<RUN>")
    assert _tree(home, (first, second, third)) == sorted(expected)
