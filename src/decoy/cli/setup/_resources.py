"""The resources section of `decoy setup`: max memory and threads."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import typer

from decoy import _resources


def _check_memory(text: str) -> str:
    if _resources.parse_memory(text) is None:
        raise typer.BadParameter(str(_resources.ResourceError("max_memory", "size")))
    return text


def _check_threads(text: str) -> int | str:
    value = _resources.parse_threads(text)
    if value is None:
        raise typer.BadParameter(str(_resources.ResourceError("threads", "count")))
    return value


class ResourcesSection:
    name = "resources"
    title = "Resources"

    def propose(self, stored: Mapping[str, Any]) -> dict[str, Any]:
        memory, threads = _resources.detect()
        saved = stored.get("max_memory", memory)
        return {
            "max_memory": saved if saved == _resources.AUTO else _resources.format_size(saved),
            "threads": stored.get("threads", threads),
        }

    def ask(
        self,
        proposed: Mapping[str, Any],
        prompt: Callable[[str, str, Callable[[str], Any]], Any],
    ) -> dict[str, Any]:
        return {
            "max_memory": prompt(
                "Max memory (size or auto)", str(proposed["max_memory"]), _check_memory
            ),
            "threads": prompt("Threads (number or auto)", str(proposed["threads"]), _check_threads),
        }

    def render(self, values: Mapping[str, Any]) -> list[str]:
        threads = values["threads"]
        shown = str(threads) if isinstance(threads, int) else f'"{threads}"'
        return [f"[{self.name}]", f'max_memory = "{values["max_memory"]}"', f"threads = {shown}"]
