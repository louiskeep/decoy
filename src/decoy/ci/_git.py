"""The one place Decoy shells out to Git for CI checks.

Trust boundary: the repository (config, attributes, refs, index, blobs, filenames) is
untrusted. Every call uses an argv array with `shell=False`, the repository root as cwd,
a scrubbed environment, a shared time budget, and flags that stop repository-configured
programs from running (`--no-ext-diff`/`--no-textconv` per call, `core.fsmonitor=false`,
no replace refs so a blob id always names the bytes it hashes, literal pathspecs).

Errors carry a fixed message; raw stderr rides in `.raw` for the unsafe debug sink only.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import time
from pathlib import Path

# Passed through because the INVOKER (hook runner, CI) sets them to say which repository
# and index this run is about; everything else, notably anything that can name a program
# to execute (pagers, editors, askpass, ssh, external diff, config injection), is dropped.
_PASSTHROUGH = (
    "PATH",
    "HOME",
    "XDG_CONFIG_HOME",
    "TMPDIR",
    "SYSTEMROOT",
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_CEILING_DIRECTORIES",
    "GIT_DISCOVERY_ACROSS_FILESYSTEM",
)

MAX_OUTPUT_BYTES = 64 * 1024 * 1024


class GitFailure(Exception):
    """A Git invocation failed, timed out, or returned unusable output."""

    def __init__(self, raw: str = "") -> None:
        super().__init__("git failure")
        self.raw = raw

    def __str__(self) -> str:
        return "git failure"


class GitBudget:
    """A wall-clock allowance shared by every Git call in one check."""

    def __init__(self, seconds: float) -> None:
        self._deadline = time.monotonic() + float(seconds)

    def remaining(self) -> float:
        return self._deadline - time.monotonic()


def git_env() -> dict[str, str]:
    env = {k: os.environ[k] for k in _PASSTHROUGH if k in os.environ}
    env.update(
        {
            "LC_ALL": "C",
            "LANG": "C",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_NO_REPLACE_OBJECTS": "1",
        }
    )
    return env


def run_git(
    args: list[str],
    cwd: Path,
    budget: GitBudget,
    *,
    stdin: bytes | None = None,
) -> bytes:
    """Run `git <args>` and return stdout; raise GitFailure on any failure."""
    remaining = budget.remaining()
    if remaining <= 0:
        raise GitFailure("time budget exhausted before git started")
    argv = [
        "git",
        "--no-pager",
        "--no-replace-objects",
        "--literal-pathspecs",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.quotepath=false",
        *args,
    ]
    try:
        proc = subprocess.Popen(
            argv,
            cwd=cwd,
            stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=git_env(),
            shell=False,
            # A new session lets a timeout kill git AND anything it spawned; otherwise a
            # grandchild holding the pipes would keep `communicate` blocked past the budget.
            start_new_session=True,
        )
    except OSError as exc:
        raise GitFailure(f"git could not be started: {exc}") from exc
    try:
        stdout, stderr = proc.communicate(stdin, timeout=remaining)
    except subprocess.TimeoutExpired as exc:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        raise GitFailure("git timed out") from exc
    if proc.returncode != 0:
        raise GitFailure(stderr.decode("utf-8", "replace"))
    if len(stdout) > MAX_OUTPUT_BYTES:
        raise GitFailure("git output exceeded the safety cap")
    return stdout


def toplevel(directory: Path, budget: GitBudget) -> Path | None:
    """The Git work-tree root containing `directory`, or None outside a work tree."""
    try:
        out = run_git(["rev-parse", "--show-toplevel"], directory, budget)
    except GitFailure:
        return None
    text = out.decode("utf-8", "surrogateescape").rstrip("\n")
    return Path(text).resolve() if text else None
