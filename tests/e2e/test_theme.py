"""Tests for the semantic-token theme module.

Covers CLI_UX_GUIDE.md section 5: every token has a helper, helpers return
Text styled with the token name, the Rich Theme resolves each token.
"""

from __future__ import annotations

from rich.text import Text

from decoy.ui import theme


SECTION_5_TOKENS = (
    "success",
    "error",
    "warn",
    "info",
    "hint",
    "accent",
    "code",
    "risk_high",
    "risk_med",
)


def test_every_section_5_token_has_a_helper():
    for token in SECTION_5_TOKENS:
        assert callable(getattr(theme, token, None)), (
            f"missing helper for token '{token}' -- "
            f"CLI_UX_GUIDE.md section 5 requires it"
        )


def test_helpers_return_text_styled_with_token_name():
    for token in SECTION_5_TOKENS:
        helper = getattr(theme, token)
        rendered = helper("sample")
        assert isinstance(rendered, Text)
        assert rendered.style == token, (
            f"helper '{token}' returned style {rendered.style!r}, expected {token!r}"
        )


def test_decoy_theme_defines_each_token():
    for token in SECTION_5_TOKENS:
        assert token in theme.DECOY_THEME.styles, (
            f"DECOY_THEME missing entry for token '{token}'"
        )
        style = theme.DECOY_THEME.styles[token]
        # A non-empty Style: at least one color or attr set.
        assert style != "" and str(style) != ""


def test_token_styles_match_section_5_defaults():
    expected = {
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
    assert theme.TOKEN_STYLES == expected
