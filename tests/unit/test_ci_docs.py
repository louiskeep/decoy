"""The CI contract document cannot drift from the registries it describes."""

from __future__ import annotations

from pathlib import Path

from decoy.ci import contracts
from decoy.cli import exit_codes

ROOT = Path(__file__).resolve().parents[2]
DOC = (ROOT / "docs" / "ci-contracts.md").read_text(encoding="utf-8")


def test_every_reason_code_and_note_id_is_documented() -> None:
    missing = [c for c in sorted(contracts.REASON_CODES) if f"`{c}`" not in DOC]
    assert not missing, missing
    assert all(f"`{n}`" in DOC for n in contracts.NOTE_TEXTS)


def test_exit_table_matches_the_public_constants() -> None:
    for name in (
        "EXIT_OK",
        "EXIT_USAGE",
        "EXIT_WARNINGS",
        "EXIT_RUNTIME",
        "EXIT_FINDINGS",
        "EXIT_CAPACITY",
    ):
        value = getattr(exit_codes, name)
        assert f"| {value} | `{name}` |" in DOC, name
    assert "**5 > 3 > 1 > 4 > 2 > 0**" in DOC
    assert contracts.EXIT_PRECEDENCE == (5, 3, 1, 4, 2, 0)


def test_documented_limits_equal_the_enforced_maxima() -> None:
    assert (
        contracts.HARD_MAX_FILES == 200 and "| `max_files` (in-scope staged files) | 200 |" in DOC
    )
    assert contracts.HARD_MAX_BLOB_BYTES == 1 << 20 and "| `max_blob_bytes` | 1 MiB |" in DOC
    assert contracts.HARD_MAX_TOTAL_BYTES == 5 << 20 and "| `max_total_bytes` | 5 MiB |" in DOC
    assert contracts.HARD_MAX_FINDING_GROUPS == 100 and "| `max_finding_groups` | 100 |" in DOC
    assert (
        contracts.HARD_MAX_GIT_SECONDS == 10 and "| `max_git_seconds` (all Git calls) | 10 |" in DOC
    )
    assert contracts.MAX_PATTERNS == 32 and contracts.LITERAL_MAX_BYTES == 128


def test_deferred_features_are_stated_not_implied() -> None:
    for phrase in ("F12", "F16", "F18", "Marketplace", "live GitHub/GitLab acceptance"):
        assert phrase in DOC, phrase


def test_registry_messages_are_fixed_authored_text() -> None:
    for message_id, text in contracts.SAFE_MESSAGES.items():
        assert message_id.startswith("ci.") and text and "{" not in text and "%s" not in text
