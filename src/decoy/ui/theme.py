"""Semantic color tokens for the decoy CLI.

Single source of truth for color decisions - every CLI-side print flows
through one of the helpers below, never raw ANSI or raw Rich markup.
See CLI_UX_GUIDE.md section 5.
"""

from __future__ import annotations

from rich.style import Style
from rich.text import Text
from rich.theme import Theme

TOKEN_STYLES: dict[str, str] = {
    "success": "green",
    "error": "bold red",
    "warn": "yellow",
    "info": "white",
    "hint": "dim",
    "accent": "cyan",
    "code": "bright_blue",
    "risk_high": "bold red",
    "risk_med": "yellow",
}

DECOY_THEME = Theme({name: Style.parse(style) for name, style in TOKEN_STYLES.items()})


def _styled(s: str, token: str) -> Text:
    return Text(s, style=token)


def success(s: str) -> Text:
    return _styled(s, "success")


def error(s: str) -> Text:
    return _styled(s, "error")


def warn(s: str) -> Text:
    return _styled(s, "warn")


def info(s: str) -> Text:
    return _styled(s, "info")


def hint(s: str) -> Text:
    return _styled(s, "hint")


def accent(s: str) -> Text:
    return _styled(s, "accent")


def code(s: str) -> Text:
    return _styled(s, "code")


def risk_high(s: str) -> Text:
    return _styled(s, "risk_high")


def risk_med(s: str) -> Text:
    return _styled(s, "risk_med")
