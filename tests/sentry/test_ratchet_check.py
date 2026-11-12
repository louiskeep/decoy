"""AT-CI0: ``scripts/dev/ratchet_check.py`` rejects every way to grow or launder a baseline.

Each case builds a scratch git repo, commits a base, edits the working tree, and runs the real
script against the base commit. Sentry ids and reasons here are synthetic.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from tests.sentry.layout import MAX_VALUE_CASES

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "dev" / "ratchet_check.py"
REASON = "reviewed on 2026-11-04, tracked for removal"
REG = "scripts/dev/sentry_registry.toml"
A = "tests/sentry/baselines/a.json"
N = "tests/sentry/baselines/n.json"
_MISSING = object()


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _baseline(
    sentry_id: str, keys: list[str], created_in: object = "S0", reason: str = REASON
) -> str:
    doc: dict[str, object] = {"sentry_id": sentry_id}
    if created_in is not _MISSING:
        doc["created_in"] = created_in
    doc["entries"] = {k: {"reason": reason} for k in keys}
    return json.dumps(doc)


def _registry(rows: dict[str, str]) -> str:
    return "".join(f'[[sentry]]\nid = "{i}"\nbaseline = "{p}"\n\n' for i, p in rows.items())


def _write(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _write(tmp_path, REG, _registry({"a": A}))
    _write(tmp_path, A, _baseline("a", ["m::f", "m::g"]))
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


def _run(repo: Path, *extra: str, base: bool = True) -> subprocess.CompletedProcess[str]:
    argv = [sys.executable, str(SCRIPT), "--root", str(repo)]
    return subprocess.run(
        [*argv, *(("--base", "HEAD") if base else ()), *extra],
        capture_output=True,
        text=True,
    )


def _assert_red(repo: Path, needle: str, *extra: str) -> None:
    res = _run(repo, *extra)
    assert res.returncode == 1, res.stdout + res.stderr
    assert needle in res.stdout + res.stderr


def test_unchanged_baseline_passes(repo: Path) -> None:
    res = _run(repo)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "a: 2 key(s)" in res.stdout


def test_shrinking_a_baseline_passes(repo: Path) -> None:
    _write(repo, A, _baseline("a", ["m::f"]))
    assert _run(repo).returncode == 0


def test_baseline_gaining_a_key_fails(repo: Path) -> None:
    # Same key count as the base: only a set comparison catches the swap.
    _write(repo, A, _baseline("a", ["m::f", "m::new"]))
    _assert_red(repo, "gained key(s) not in the merge base: m::new")


# The last two clear MIN_REASON, so only the placeholder rule can reject them.
PLACEHOLDER_REASONS = [
    "",
    "   ",
    "todo",
    "TBD.",
    "FIXME",
    "too short",
    "todo" + "." * 11,
    "N/A!!!!!!!!!!!!",
]


@pytest.mark.parametrize("reason", PLACEHOLDER_REASONS)
def test_empty_or_placeholder_reason_fails(repo: Path, reason: str) -> None:
    _write(repo, A, _baseline("a", ["m::f"], reason=reason))
    _assert_red(repo, "reason for m::f is empty, a placeholder or under")


def test_renamed_baseline_with_extra_key_fails(repo: Path) -> None:
    (repo / A).unlink()
    new = "tests/sentry/baselines/b.json"
    _write(repo, new, _baseline("b", ["m::f", "m::g", "m::extra"]))
    _write(repo, REG, _registry({"b": new}))
    _assert_red(repo, "replacement or split of a adds key(s): m::extra")


def test_moved_baseline_for_a_kept_id_fails(repo: Path) -> None:
    (repo / A).unlink()
    new = "tests/sentry/baselines/b.json"
    _write(repo, new, _baseline("a", ["m::f"]))
    _write(repo, REG, _registry({"a": new}))
    _assert_red(repo, "baseline moved from")


def test_replaced_baseline_with_new_sentry_id_fails(repo: Path) -> None:
    _write(repo, A, _baseline("a2", ["m::f", "m::g", "m::extra"]))
    _write(repo, REG, _registry({"a2": A}))
    _assert_red(repo, "m::extra")


def test_split_whose_union_adds_a_key_fails(repo: Path) -> None:
    (repo / A).unlink()
    _write(repo, "tests/sentry/baselines/a1.json", _baseline("a1", ["m::f"]))
    _write(repo, "tests/sentry/baselines/a2.json", _baseline("a2", ["m::g", "m::extra"]))
    reg = {"a1": "tests/sentry/baselines/a1.json", "a2": "tests/sentry/baselines/a2.json"}
    _write(repo, REG, _registry(reg))
    _assert_red(repo, "adds key(s): m::extra")


def test_split_keeping_the_union_passes(repo: Path) -> None:
    (repo / A).unlink()
    _write(repo, "tests/sentry/baselines/a1.json", _baseline("a1", ["m::f"]))
    _write(repo, "tests/sentry/baselines/a2.json", _baseline("a2", ["m::g"]))
    reg = {"a1": "tests/sentry/baselines/a1.json", "a2": "tests/sentry/baselines/a2.json"}
    _write(repo, REG, _registry(reg))
    res = _run(repo, "--slice", "X0a")
    assert res.returncode == 0, res.stdout + res.stderr


def test_new_baseline_without_registry_entry_fails(repo: Path) -> None:
    _write(repo, "tests/sentry/baselines/z.json", _baseline("z", ["m::z"]))
    _assert_red(repo, "tests/sentry/baselines/z.json: baseline file is not registered")


def test_registry_entry_without_baseline_file_fails(repo: Path) -> None:
    _write(repo, REG, _registry({"a": A, "b": "tests/sentry/baselines/b.json"}))
    _assert_red(repo, "no baseline file")


def test_two_ids_for_one_path_fail(repo: Path) -> None:
    _write(repo, REG, _registry({"a": A, "a-twin": A}))
    _assert_red(repo, "two sentries")


def test_registry_path_outside_baseline_dir_fails(repo: Path) -> None:
    _write(repo, "elsewhere/n.json", _baseline("n", ["m::one"]))
    _write(repo, REG, _registry({"a": A, "n": "elsewhere/n.json"}))
    _assert_red(repo, "is outside tests/sentry/baselines/")


def test_duplicate_registry_id_fails(repo: Path) -> None:
    _write(repo, REG, _registry({"a": A}) + f'[[sentry]]\nid = "a"\nbaseline = "{A}"\n')
    _assert_red(repo, "sentry id a appears twice")


def test_baseline_id_must_match_registry_id(repo: Path) -> None:
    _write(repo, A, _baseline("other", ["m::f"]))
    _assert_red(repo, "sentry_id")


def test_new_sentry_with_its_first_inventory_in_one_diff_passes(repo: Path) -> None:
    _write(repo, N, _baseline("n", ["m::one", "m::two", "m::three"], created_in="X9"))
    _write(repo, REG, _registry({"a": A, "n": N}))
    res = _run(repo)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "n: first inventory, 3 key(s), review required" in res.stdout


def test_first_inventory_created_in_must_match_slice(repo: Path) -> None:
    _write(repo, N, _baseline("n", ["m::one"], created_in="S0"))
    _write(repo, REG, _registry({"a": A, "n": N}))
    _assert_red(repo, "n: created_in 'S0' is not slice 'X0a'", "--slice", "X0a")
    res = _run(repo, "--slice", "S0")
    assert res.returncode == 0, res.stdout + res.stderr


def test_padded_created_in_does_not_match_the_slice(repo: Path) -> None:
    _write(repo, N, _baseline("n", ["m::one"], created_in=" X0a "))
    _write(repo, REG, _registry({"a": A, "n": N}))
    _assert_red(repo, "n: created_in ' X0a ' is not slice 'X0a'", "--slice", "X0a")


def test_kept_sentry_is_not_held_to_the_slice(repo: Path) -> None:
    # created_in names the slice that first inventoried a baseline; later slices only shrink it.
    _write(repo, A, _baseline("a", ["m::f"]))
    assert _run(repo, "--slice", "X0a").returncode == 0


@pytest.mark.parametrize("created_in", [_MISSING, "", "  ", 7])
def test_missing_created_in_fails(repo: Path, created_in: object) -> None:
    _write(repo, A, _baseline("a", ["m::f"], created_in=created_in))
    _assert_red(repo, f"{A}: created_in is missing or not a non-empty string")


def test_env_var_does_not_allow_growth(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("RATCHET_ALLOW_GROWTH", "RATCHET_SLICE", "RATCHET_ALLOW", "CI"):
        monkeypatch.setenv(name, "1")
    assert os.environ["RATCHET_ALLOW_GROWTH"] == "1"
    _write(repo, A, _baseline("a", ["m::f", "m::g", "m::new"]))
    _assert_red(repo, "m::new")


def test_growth_fails_even_when_the_registry_is_also_edited(repo: Path) -> None:
    _write(repo, A, _baseline("a", ["m::f", "m::g", "m::new"]))
    _write(repo, N, _baseline("n", ["m::one"]))
    _write(repo, REG, _registry({"a": A, "n": N}))
    _assert_red(repo, "m::new")


def test_no_merge_base_exits_2(repo: Path) -> None:
    res = _run(repo, base=False)
    assert res.returncode == 2, res.stdout + res.stderr
    assert "run: git fetch origin main" in res.stderr


# --- moved_from: exact one-to-one key moves (RUN-SPLIT) ---------------------------------------


def _moved(
    entries: dict[str, object], moved: object, sentry_id: str = "a", created_in: str = "S0"
) -> str:
    doc: dict[str, object] = {"sentry_id": sentry_id, "created_in": created_in, "entries": entries}
    doc["moved_from"] = moved
    return json.dumps(doc)


def _entry(**extra: object) -> dict[str, object]:
    return {"reason": REASON, **extra}


def test_one_exact_move_passes_with_counts_unchanged(repo: Path) -> None:
    _write(repo, A, _moved({"m::f": _entry(), "n::g": _entry()}, {"n::g": "m::g"}))
    res = _run(repo)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "a: 2 key(s)" in res.stdout


def test_several_exact_moves_pass(repo: Path) -> None:
    _write(repo, A, _moved({"n::f": _entry(), "n::g": _entry()}, {"n::f": "m::f", "n::g": "m::g"}))
    res = _run(repo)
    assert res.returncode == 0, res.stdout + res.stderr


def test_move_does_not_admit_a_second_new_key(repo: Path) -> None:
    entries = {"n::f": _entry(), "m::g": _entry(), "n::extra": _entry()}
    _write(repo, A, _moved(entries, {"n::f": "m::f"}))
    _assert_red(repo, "gained key(s) not in the merge base: n::extra")


def test_move_with_old_key_still_present_fails(repo: Path) -> None:
    entries = {"m::f": _entry(), "m::g": _entry(), "n::g": _entry()}
    _write(repo, A, _moved(entries, {"n::g": "m::g"}))
    _assert_red(repo, "old key m::g is still in the head")


def test_two_new_keys_naming_one_old_key_fail(repo: Path) -> None:
    entries = {"m::f": _entry(), "n::g": _entry(), "o::g": _entry()}
    _write(repo, A, _moved(entries, {"n::g": "m::g", "o::g": "m::g"}))
    _assert_red(repo, "moved_from names m::g for both")


def test_move_from_a_key_not_in_the_base_fails(repo: Path) -> None:
    _write(repo, A, _moved({"m::f": _entry(), "n::g": _entry()}, {"n::g": "m::ghost"}))
    _assert_red(repo, "old key m::ghost was not in the merge base")


def test_move_to_a_key_absent_from_the_head_fails(repo: Path) -> None:
    _write(repo, A, _moved({"m::f": _entry()}, {"n::g": "m::g"}))
    _assert_red(repo, "moved_from key n::g is not an entry in the head")


def test_move_with_a_changed_reason_fails(repo: Path) -> None:
    new = {"reason": "a different reviewed reason text"}
    _write(repo, A, _moved({"m::f": _entry(), "n::g": new}, {"n::g": "m::g"}))
    _assert_red(repo, "moved entry n::g differs from m::g")


def test_move_with_a_raised_sites_value_fails(repo: Path) -> None:
    _write(repo, A, _baseline("a", ["m::f", "m::g"]).replace('"m::g": {', '"m::g": {"sites": 4, '))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base with sites")
    _write(repo, A, _moved({"m::f": _entry(), "n::g": _entry(sites=5)}, {"n::g": "m::g"}))
    _assert_red(repo, "moved entry n::g differs from m::g")


@pytest.mark.parametrize("moved", [["n::g"], "n::g", 7, True])
def test_non_object_moved_from_fails(repo: Path, moved: object) -> None:
    _write(repo, A, _moved({"m::f": _entry(), "n::g": _entry()}, moved))
    _assert_red(repo, "moved_from is not an object")


@pytest.mark.parametrize(
    "mapping",
    [
        {"": "m::g"},
        {"   ": "m::g"},
        {"n::g": ""},
        {"n::g": "  "},
        {"n::g": 7},
        {"n::g": None},
        {"n::g": ["m::g"]},
        {"n::g": True},
    ],
)
def test_malformed_moved_from_entries_fail_without_crashing(
    repo: Path, mapping: dict[str, object]
) -> None:
    _write(repo, A, _moved({"m::f": _entry(), "n::g": _entry()}, mapping))
    res = _run(repo)
    assert res.returncode == 1, res.stdout + res.stderr
    assert "Traceback" not in res.stderr
    assert "moved_from needs non-empty string keys and values" in res.stderr


def test_a_merged_move_left_in_the_map_is_ignored(repo: Path) -> None:
    # The base already holds n::g (the move merged); the map entry admits nothing and is harmless.
    _write(repo, A, _moved({"m::f": _entry(), "n::g": _entry()}, {}))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "moved")
    _write(repo, A, _moved({"m::f": _entry(), "n::g": _entry()}, {"n::g": "m::g"}))
    res = _run(repo)
    assert res.returncode == 0, res.stdout + res.stderr


# --- numeric ``max`` entries: a head value above its base value is growth --------------------

_CASES = pytest.mark.parametrize(
    ("base_max", "head_max", "red"),
    [c[1:] for c in MAX_VALUE_CASES],
    ids=[c[0] for c in MAX_VALUE_CASES],
)


def _max_baseline(sid: str, max_value: int | None) -> str:
    entry: dict[str, object] = {"reason": REASON}
    if max_value is not None:
        entry["max"] = max_value
    return json.dumps({"sentry_id": sid, "created_in": "S0", "entries": {"m::f": entry}})


@_CASES
def test_numeric_max_may_not_rise(
    repo: Path, base_max: int | None, head_max: int | None, red: bool
) -> None:
    _write(repo, A, _max_baseline("a", base_max))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "max")
    _write(repo, A, _max_baseline("a", head_max))
    res = _run(repo)
    assert (res.returncode == 1) is red, res.stdout + res.stderr
    if red:
        assert "a: max raised or dropped for key(s): m::f" in res.stderr


@_CASES
def test_a_rename_may_not_raise_a_numeric_max(
    repo: Path, base_max: int | None, head_max: int | None, red: bool
) -> None:
    _write(repo, A, _max_baseline("a", base_max))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "max")
    renamed = "tests/sentry/baselines/r.json"
    (repo / A).unlink()
    _write(repo, renamed, _max_baseline("r", head_max))
    _write(repo, REG, _registry({"r": renamed}))
    res = _run(repo)
    assert (res.returncode == 1) is red, res.stdout + res.stderr
    if red:
        assert "replacement or split of a raised or dropped max for key(s): m::f" in res.stderr
