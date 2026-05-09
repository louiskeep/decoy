"""Starter pipeline templates bundled with the decoy CLI.

Each `.yaml` file in this directory is exposed via `decoy templates list`
and dumped to stdout via `decoy templates show <name>`. The same set is
also offered as a preset by `decoy init`.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from typing import Iterator


@dataclass(frozen=True)
class Template:
    name: str
    summary: str
    body: str


# Order is the listing order in `decoy templates list`. Summaries echo into
# the listing table and the `decoy init` preset prompt.
_REGISTRY: tuple[tuple[str, str], ...] = (
    ("minimal", "Bare-bones masking: name / email / SSN. Smallest sensible starting point."),
    ("hipaa", "HIPAA Safe Harbor coverage: 18 PHI identifiers mapped to faker / hash / redact."),
    ("pci", "PCI DSS card-data masking: PAN, CVV, cardholder name, expiration."),
    ("gdpr", "GDPR personal-data masking: name, email, phone, IP address, location."),
    ("generate", "Synthetic-data generation pipeline; no input file required."),
    ("graph", "Graph-mode pipeline: nodes + edges instead of flat masking_rules."),
)


def list_templates() -> list[Template]:
    """Return every bundled template, in registry order."""
    out: list[Template] = []
    for name, summary in _REGISTRY:
        out.append(Template(name=name, summary=summary, body=_load(name)))
    return out


def template_names() -> list[str]:
    """Just the names -- used by tab completion."""
    return [name for name, _ in _REGISTRY]


def get_template(name: str) -> Template | None:
    """Look up a single template by name. None if unknown."""
    for n, summary in _REGISTRY:
        if n == name:
            return Template(name=n, summary=summary, body=_load(n))
    return None


def _load(name: str) -> str:
    """Read the bundled YAML file using importlib.resources.

    Going through `resources` keeps templates working when the package
    is installed as a wheel rather than from source.
    """
    return resources.files(__package__).joinpath(f"{name}.yaml").read_text(encoding="utf-8")
