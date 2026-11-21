"""The kind canary registry: one runnable case per writable record kind (G-KIND-CANARY).

A case runs the kind's real producer in a fresh project folder with a canary string in every
cell. `test_canary.py` runs each case and checks both sides: a record of the kind was written
(positive) and the canary appears in no file under `.decoy/library/` or `.decoy/logs/`
(negative). The sentry reads coverage from `CASES`, so a kind is covered only by a case that
runs, never by a file name. Producers that are not built yet sit in the sentry's pending rows:
L2 adds `scan-set`, L3b `sample-run`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from decoy.cli.library import open_library

CANARY = "CANARY-decoy-7f3a9c"


@dataclass(frozen=True)
class CanaryCase:
    """`produce(project)` runs the producer command in `project` with canary data."""

    kind: str
    produce: Callable[[Path], None]


def _evidence(project: Path) -> None:
    """`decoy run` of a mask pipeline whose every cell holds the canary (L3a)."""
    from typer.testing import CliRunner

    from decoy.__main__ import app
    from tests.e2e.library.test_run_evidence_records import write_pipeline

    (project / ".git").mkdir()
    (project / "decoy.yaml").write_text("kind: decoy-project/v1\n", encoding="utf-8")
    yaml_path = write_pipeline(project, cells=(f"{CANARY}@a.example", f"{CANARY}@b.example"))
    result = CliRunner().invoke(
        app, ["run", str(yaml_path), "--mode", "mask"], env={"DECOY_LIBRARY": ""}
    )
    assert result.exit_code == 0, result.output


CASES: dict[str, CanaryCase] = {
    "evidence": CanaryCase("evidence", _evidence),
    # The same run stores both records; the run-result is the document, not the data.
    "run-result": CanaryCase("run-result", _evidence),
}


def leaks(decoy_dir: Path, canary: str = CANARY) -> list[str]:
    """Every file under `library/` and `logs/` that holds the canary, relative to `decoy_dir`."""
    needle = canary.encode("utf-8")
    found: list[str] = []
    for folder in ("library", "logs"):
        top = decoy_dir / folder
        if not top.is_dir():
            continue
        for path in sorted(top.rglob("*")):
            if path.is_file() and not path.is_symlink() and needle in path.read_bytes():
                found.append(path.relative_to(decoy_dir).as_posix())
    return found


def kinds_written(decoy_dir: Path) -> set[str]:
    """The kinds of the records stored in the library at `decoy_dir`."""
    return {row.kind for row in open_library(decoy_dir).rows()}
