"""The CLI imports an engine reason code from its public module; it never copies the string.

A copied literal keeps passing every behavior test until the engine renames the code, then the
CLI silently stops matching it. This sentry scans every `.py` under `src/decoy` for a string
constant equal to a code in the engine's public registry (`decoy_engine.reasons.specs()`).

Filters, each on purpose:
- Docstrings (module, class, function) are prose and are skipped.
- A code without `_` or `.` is skipped. Those are single English words (`invalid`, `other`,
  `eligible`) that appear in the CLI as ordinary text; matching them would flag prose, not copies.
- Matching is exact string equality, so a longer message that merely contains a code is not a copy.

Legacy copies are frozen in `ALLOWLIST` (mirrored in `baselines/engine-reason-code-copies.json`,
shrink-only). A new (file, code) pair, a higher count, a stale entry (pair gone) or a count that
fell all fail, so the list only shrinks. Some entries are dict keys or section names that happen to
equal a code; they stay listed because the scan cannot tell them from a copied code.

Named limits: codes built at run time, and strings inside f-string pieces other than a whole
constant part, are not seen.
"""

from __future__ import annotations

import ast
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "src" / "decoy"


@dataclass(frozen=True)
class AllowedCopy:
    file: str  # path relative to src/decoy
    code: str
    count: int  # exact occurrences allowed; more or fewer fail
    reason: str


_COPY = "Legacy copy of an engine reason code; import the engine constant, then delete this entry."
_KEY = (
    "Dict key or section name that equals an engine code, not a code the CLI matches; "
    "rename or delete this entry once the scan can tell them apart."
)


def _copy(file: str, code: str, count: int = 1) -> AllowedCopy:
    return AllowedCopy(file, code, count, _COPY)


def _key(file: str, code: str, count: int) -> AllowedCopy:
    return AllowedCopy(file, code, count, _KEY)


ALLOWLIST: tuple[AllowedCopy, ...] = (
    _copy("_mask_secret.py", "secret_file_permissions_unsafe"),
    _copy("_mask_secret_guidance.py", "keyed_strategy_requires_secret"),
    _copy("_mask_secret_guidance.py", "weak_mask_secret"),
    _copy("_mask_secret_guidance.py", "missing_mask_secret"),
    _copy("_mask_secret_guidance.py", "bad_secret_ref"),
    _copy("_mask_secret_guidance.py", "secret_provider_unknown"),
    _copy("_mask_secret_guidance.py", "secret_file_permissions_unsafe"),
    _copy("cli/extras.py", "ner_spacy_not_installed"),
    _key("cli/fit.py", "row_count", 2),
    _copy("cli/fit.py", "dp_numeric_domain_invalid", 2),
    _copy("cli/fit.py", "dp_schedule_mismatch", 2),
    _key("cli/gen/_preview.py", "row_count", 2),
    _key("cli/gen/_scaffold.py", "row_count", 2),
    _key("cli/io/_scan_set.py", "row_count", 3),
    _copy("cli/preflight.py", "out_of_core_fanin_exceeds_budget"),
    _copy("cli/preflight.py", "capacity_source_unprofilable"),
    _copy("cli/report.py", "vault_protocol_version_mismatch"),
    _copy("cli/run/_errors.py", "uniqueness_impossible"),
    _key("cli/run/_execute.py", "fidelity_report", 1),
    _key("cli/run/_execute.py", "post_validation", 1),
    _copy("cli/scanning/_multi.py", "scan_header_suspect"),
    _copy("cli/scanning/_multi.py", "scan_key_type_mismatch"),
    _key("cli/scanning/_multi.py", "row_count", 6),
    _copy("cli/subset.py", "subset_config_missing"),
    _copy("cli/unmask.py", "vault_protocol_version_mismatch"),
    _key("notify.py", "row_count", 3),
    _copy("ui/summary.py", "null_drift"),
    _copy("ui/summary.py", "kind_drift"),
)


def engine_codes() -> frozenset[str]:
    from decoy_engine.reasons import specs

    return frozenset(s.code for s in specs() if "_" in s.code or "." in s.code)


def _docstring_ids(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                ids.add(id(first.value))
    return ids


def scan(src: Path, codes: frozenset[str]) -> Counter[tuple[str, str]]:
    """Count (path relative to `src`, code) for every string constant equal to an engine code."""
    found: Counter[tuple[str, str]] = Counter()
    for path in sorted(src.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        skip = _docstring_ids(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value in codes
                and id(node) not in skip
            ):
                found[(path.relative_to(src).as_posix(), node.value)] += 1
    return found


def findings(
    found: Counter[tuple[str, str]], allow: tuple[AllowedCopy, ...] = ALLOWLIST
) -> list[str]:
    allowed = {(a.file, a.code): a.count for a in allow}
    out = []
    for (file, code), n in sorted(found.items()):
        cap = allowed.get((file, code))
        if cap is None:
            out.append(f"{file}: copies engine reason code {code!r} ({n}x); import it instead")
        elif n > cap:
            out.append(f"{file}: {code!r} appears {n}x, allowlist holds {cap}")
    for (file, code), cap in sorted(allowed.items()):
        n = found.get((file, code), 0)
        if n < cap:
            out.append(
                f"{file}: stale allowlist entry {code!r} (allows {cap}, found {n}); shrink it"
            )
    return out


def test_no_new_engine_reason_code_copies_in_cli_source() -> None:
    assert findings(scan(_SRC, engine_codes())) == []


def test_allowlist_entries_are_unique_and_explained() -> None:
    keys = [(a.file, a.code) for a in ALLOWLIST]
    assert len(set(keys)) == len(keys)
    assert all(len(a.reason.strip()) >= 15 and a.count >= 1 for a in ALLOWLIST)
    assert all((_SRC / a.file).is_file() for a in ALLOWLIST)


# Seeded runs on temp trees: the sentry must see a copy, and must not see a docstring.
_CODE = "statistical_real_categories_not_allowed"


def _tree(tmp_path: Path, body: str) -> Path:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text(body, encoding="utf-8")
    return tmp_path


def test_seeded_copied_code_is_red(tmp_path: Path) -> None:
    src = _tree(tmp_path, f'CODE = "{_CODE}"\n')
    assert _CODE in engine_codes()
    assert findings(scan(src, engine_codes()), ()) == [
        f"pkg/mod.py: copies engine reason code {_CODE!r} (1x); import it instead"
    ]


def test_seeded_docstring_mention_is_green(tmp_path: Path) -> None:
    body = (
        f'"""Mentions {_CODE}."""\n\nclass C:\n    """{_CODE}"""\n\ndef f():\n    """{_CODE}"""\n'
    )
    assert findings(scan(_tree(tmp_path, body), engine_codes()), ()) == []


def test_seeded_docstring_that_is_exactly_a_code_is_green(tmp_path: Path) -> None:
    assert findings(scan(_tree(tmp_path, f'"{_CODE}"\n'), engine_codes()), ()) == []


def test_seeded_stale_and_lowered_allowlist_entries_are_red(tmp_path: Path) -> None:
    src = _tree(tmp_path, f'A = "{_CODE}"\n')
    gone = (AllowedCopy("pkg/gone.py", _CODE, 1, _COPY),)
    assert any("stale" in f for f in findings(scan(src, engine_codes()), gone))
    lowered = (AllowedCopy("pkg/mod.py", _CODE, 2, _COPY),)
    assert any("stale" in f for f in findings(scan(src, engine_codes()), lowered))
    raised = (AllowedCopy("pkg/mod.py", _CODE, 1, _COPY),)
    assert findings(scan(src, engine_codes()), raised) == []


def test_seeded_higher_count_is_red(tmp_path: Path) -> None:
    src = _tree(tmp_path, f'A = "{_CODE}"\nB = "{_CODE}"\n')
    held = (AllowedCopy("pkg/mod.py", _CODE, 1, _COPY),)
    assert findings(scan(src, engine_codes()), held) == [
        f"pkg/mod.py: {_CODE!r} appears 2x, allowlist holds 1"
    ]


def test_seeded_scaffold_with_the_literal_put_back_is_red(tmp_path: Path) -> None:
    text = (_SRC / "cli" / "gen" / "_scaffold.py").read_text(encoding="utf-8")
    imp = "    from decoy_engine.reasons.plan import STATISTICAL_REAL_CATEGORIES_NOT_ALLOWED as opt_in_code\n"
    assert imp in text, "scaffold no longer imports the engine constant"
    (tmp_path / "cli" / "gen").mkdir(parents=True)
    (tmp_path / "cli" / "gen" / "_scaffold.py").write_text(
        text.replace(imp, f'    opt_in_code = "{_CODE}"\n'), encoding="utf-8"
    )
    own = tuple(a for a in ALLOWLIST if a.file == "cli/gen/_scaffold.py")
    assert findings(scan(tmp_path, engine_codes()), own) == [
        f"cli/gen/_scaffold.py: copies engine reason code {_CODE!r} (1x); import it instead"
    ]
    # With the real import kept, the same file is clean.
    (tmp_path / "cli" / "gen" / "_scaffold.py").write_text(text, encoding="utf-8")
    assert findings(scan(tmp_path, engine_codes()), own) == []


@pytest.mark.parametrize("code", ["invalid", "other"])
def test_single_word_codes_are_out_of_scope(code: str) -> None:
    assert code not in engine_codes()
