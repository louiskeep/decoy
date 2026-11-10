"""The ordered list of `decoy setup` sections.

Each section owns one table of `settings.toml`. The order here is the order in the file and the
order of the prompts. A later feature appends its section to `SECTIONS`; nothing else changes.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Protocol

from decoy.cli.setup._resources import ResourcesSection

Ask = Callable[[str, str, Callable[[str], Any]], Any]


class Section(Protocol):
    name: str
    title: str

    def propose(self, stored: Mapping[str, Any]) -> dict[str, Any]:
        """Values to offer: what the file holds, else what this host reports."""

    def ask(self, proposed: Mapping[str, Any], prompt: Ask) -> dict[str, Any]:
        """Let the user confirm or change each proposed value."""

    def render(self, values: Mapping[str, Any]) -> list[str]:
        """The TOML lines of this section's table."""


SECTIONS: tuple[Section, ...] = (ResourcesSection(),)
