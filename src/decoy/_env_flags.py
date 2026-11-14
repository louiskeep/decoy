"""The CLI's one reader for environment switches (stub)."""

from __future__ import annotations


def safe_env_flag(name: str, *, default: bool, unknown: bool) -> bool:
    return default


def is_ci() -> bool:
    return False


def no_color() -> bool:
    return False


def env_int(name: str, default: int) -> int:
    return default
