"""Stub: the pipeline token parser and resolver (filled in by the next commit)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import typer


@dataclass(frozen=True)
class PipelineToken:
    raw: str
    kind: str
    project_flag: Path | None = None


@dataclass(frozen=True)
class PipelineRef:
    yaml: Path
    project: object
    name: str | None
    given_as: str


@dataclass(frozen=True)
class PipelineEntry:
    name: str
    yaml: Path


def parse_pipeline_token(ctx: typer.Context, value: str | None) -> str | None:
    return value


def resolve_pipeline(token: object, state: object, command: str) -> None:
    return None


def list_pipelines(project: object) -> list[PipelineEntry]:
    return []


def explicit_project(ctx: typer.Context | None) -> Path | None:
    return None
