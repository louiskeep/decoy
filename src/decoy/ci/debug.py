"""The one sanctioned raw sink: `--unsafe-debug-log PATH`.

Raw exception text, tracebacks, and subprocess stderr may contain secrets, sample values,
and absolute paths. They go ONLY here, into a file the operator explicitly named, and never
to stdout/stderr or any report. Nothing is created unless a path was given.
"""

from __future__ import annotations

import os
import tempfile
import traceback
from pathlib import Path


class DebugSink:
    def __init__(self, path: Path | None) -> None:
        self._path = path
        self._lines: list[str] = []

    @property
    def enabled(self) -> bool:
        return self._path is not None

    def add(self, label: str, text: str = "") -> None:
        if self._path is not None:
            self._lines.append(f"[{label}] {text}".rstrip())

    def add_exception(self, label: str) -> None:
        if self._path is not None:
            self._lines.append(f"[{label}]\n{traceback.format_exc().rstrip()}")

    def add_all(self, label: str, texts: list[str]) -> None:
        for text in texts:
            if text:
                self.add(label, text)

    def flush(self) -> None:
        if self._path is None:
            return
        header = "# decoy ci check UNSAFE debug log: may contain secrets and sample values.\n"
        body = header + "\n".join(self._lines) + "\n"
        directory = self._path.parent
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".decoy-debug-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", errors="replace") as handle:
                handle.write(body)
            os.replace(tmp, self._path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
