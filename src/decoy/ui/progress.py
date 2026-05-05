"""Progress patterns -- spinner, bar, multistage. See CLI_UX_GUIDE.md section 7.

All progress streams to stderr. Auto-disabled when --quiet or stderr is not
a TTY. Commands receive an `OutputState` and pass `state.err_console` (or
`state` itself) into these helpers.
"""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
from typing import Iterator

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from decoy.ui.output import OutputMode, OutputState


def _disabled(state: OutputState) -> bool:
    """Progress is suppressed in quiet mode or when stderr is not a TTY."""
    return state.mode is OutputMode.quiet or not state.err_console.is_terminal


@contextmanager
def spinner(state: OutputState, message: str) -> Iterator[None]:
    """Indeterminate spinner. Use for ops < ~10s with no progress signal."""
    if _disabled(state):
        yield
        return
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[info]{task.description}[/info]"),
        TimeElapsedColumn(),
        console=state.err_console,
        transient=True,
    )
    with progress:
        progress.add_task(message, total=None)
        yield


class _BarHandle:
    def __init__(self, progress: Progress | None, task_id: int | None) -> None:
        self._progress = progress
        self._task_id = task_id

    def advance(self, n: int = 1) -> None:
        if self._progress is not None and self._task_id is not None:
            self._progress.advance(self._task_id, n)


@contextmanager
def progress_bar(
    state: OutputState,
    *,
    total: int,
    label: str,
) -> Iterator[_BarHandle]:
    """Known-length bar with percent / ETA / throughput."""
    if _disabled(state) or total <= 0:
        yield _BarHandle(None, None)
        return
    progress = Progress(
        TextColumn("[info]{task.description}[/info]"),
        BarColumn(),
        TextColumn("{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=state.err_console,
        transient=True,
    )
    with progress:
        task_id = progress.add_task(label, total=total)
        yield _BarHandle(progress, task_id)


class _MultistageHandle:
    """Advances through a fixed sequence of named stages.

    Stage labels render as `[<icon>] <label>` lines: `[ ]` pending, `[*]` running,
    `[v]` done. ASCII fallbacks per CLI_UX_GUIDE.md section 14 -- no Unicode
    arrows, em-dashes, or box-drawing.
    """

    PENDING = " "
    RUNNING = "*"
    DONE = "v"

    def __init__(
        self,
        progress: Progress | None,
        task_ids: list[int] | None,
        labels: list[str],
    ) -> None:
        self._progress = progress
        self._task_ids = task_ids
        self._labels = labels
        self._idx = 0

    def _render(self, idx: int) -> None:
        if self._progress is None or self._task_ids is None:
            return
        for i, task_id in enumerate(self._task_ids):
            if i < idx:
                icon = self.DONE
            elif i == idx:
                icon = self.RUNNING
            else:
                icon = self.PENDING
            self._progress.update(
                task_id,
                description=f"[{icon}] {self._labels[i]}",
            )

    def start(self) -> None:
        self._render(self._idx)

    def complete(self) -> None:
        """Mark the current stage done and advance to the next."""
        self._idx += 1
        self._render(self._idx)


@contextmanager
def multistage(state: OutputState, stages: list[str]) -> Iterator[_MultistageHandle]:
    """Multi-stage indicator for pipelines.

    Usage:
        with multistage(state, ["Load", "Profile", "Score"]) as ms:
            do_load()
            ms.complete()
            do_profile()
            ms.complete()
            do_score()
    """
    if _disabled(state) or not stages:
        yield _MultistageHandle(None, None, stages)
        return
    progress = Progress(
        TextColumn("{task.description}"),
        TimeElapsedColumn(),
        console=state.err_console,
        transient=True,
    )
    with progress:
        task_ids = [
            progress.add_task(f"[ ] {label}", total=None) for label in stages
        ]
        handle = _MultistageHandle(progress, task_ids, stages)
        handle.start()
        yield handle
