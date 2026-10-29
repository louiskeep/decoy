"""Single-flight lock serializing every mutation of one managed installation.

Staging, the ``current`` flip, post-swap validation, rollback, reclamation, and pruning
all read-then-write the shared ``versions/`` + ``current`` state, so two overlapping
commands (a repair racing a repair, a bootstrap racing ``decoy upgrade``) can each delete
the slot the other just made live. One ``flock`` on ``<home>/.install.lock`` held for the
whole mutate-then-reclaim critical section removes the race at the root, rather than
re-reading ``current`` before each delete (which still leaves a check-then-act window).

Single-flight, not queueing: a held lock is an immediate refusal, so a stuck holder never
hangs a second command. ``flock`` is released by the kernel when the holder dies, so a
crash cannot leave a stale lock. Pattern: the advisory-lockfile discipline of rustup/uv/
dpkg. The shell bootstrap takes this SAME lock by running its critical section through
``decoy.distribution.first_install``. Windows is gated off the advertised matrix, so
there the lock is a no-op rather than a second implementation nobody can test.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path
from typing import Iterator

try:
    import fcntl
except ImportError:  # Windows
    fcntl = None  # type: ignore[assignment]

LOCK_NAME = ".install.lock"


class InstallBusyError(RuntimeError):
    """Another install/upgrade/repair holds the installation lock."""


BUSY_MESSAGE = (
    "another install/upgrade/repair is in progress for this installation; "
    "wait for it to finish and re-run (the existing runtime is untouched)"
)


@contextlib.contextmanager
def exclusive(home: Path) -> Iterator[None]:
    if fcntl is None:
        yield
        return
    home.mkdir(parents=True, exist_ok=True)
    # O_CLOEXEC (Python's default) keeps the fd out of spawned validators/self-checks, so
    # a child cannot outlive the holder and keep the lock.
    fd = os.open(home / LOCK_NAME, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise InstallBusyError(BUSY_MESSAGE) from exc
        yield
    finally:
        os.close(fd)
