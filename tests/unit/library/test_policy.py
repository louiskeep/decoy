"""The retention policy model (plan 4.7, L1b.3): `.decoy/library.yaml`, strict, defaults when absent.

Nothing enforces retention yet; this pins the model, the defaults and the value-free errors.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from decoy.cli.io import DECOY_DIR
from decoy.cli.library import LibraryError, LibraryPolicy, _errors, load_policy
from decoy.cli.library._errors import LIBRARY_POLICY_INVALID


@pytest.fixture
def root(tmp_path: Path) -> Path:
    folder = tmp_path / DECOY_DIR
    folder.mkdir()
    return folder


def _write(root: Path, text: str) -> None:
    (root / "library.yaml").write_text(text, encoding="utf-8")


def test_an_absent_file_means_the_plan_defaults(root: Path) -> None:
    policy = load_policy(root)
    assert policy == LibraryPolicy()
    retention = policy.retention
    assert retention.records.default.keep == "all"
    assert retention.records.kinds == {}
    assert (retention.logs.keep_last_runs_per_pipeline, retention.logs.max_age_days) == (50, 30)
    assert (retention.scratch.sample_ttl_hours, retention.scratch.staging) == (
        24,
        "delete_on_exit",
    )


def test_a_file_overrides_per_kind_and_keeps_the_other_defaults(root: Path) -> None:
    _write(
        root,
        "retention:\n"
        "  records:\n"
        "    default: {keep: all}\n"
        "    run-result: {keep_last: 500}\n"
        "  logs: {keep_last_runs_per_pipeline: 10}\n",
    )
    policy = load_policy(root)
    assert policy.retention.records.kinds["run-result"].keep_last == 500
    assert policy.retention.logs.keep_last_runs_per_pipeline == 10
    assert policy.retention.logs.max_age_days == 30  # untouched default
    assert policy.retention.scratch.sample_ttl_hours == 24


def test_an_empty_file_means_the_defaults(root: Path) -> None:
    _write(root, "")
    assert load_policy(root) == LibraryPolicy()


@pytest.mark.parametrize(
    ("text", "field"),
    [
        ("retention:\n  logs: {keep_forever: true}\n", "retention.logs.keep_forever"),
        ("retention_typo: {}\n", "retention_typo"),
        ("retention:\n  records:\n    not-a-kind: {keep: all}\n", "retention.records"),
        ("retention:\n  records:\n    evidence: {keep_last: 0}\n", "retention.records"),
    ],
)
def test_an_unknown_key_or_kind_is_refused_by_name(root: Path, text: str, field: str) -> None:
    _write(root, text)
    with pytest.raises(LibraryError) as caught:
        load_policy(root)
    assert caught.value.code == LIBRARY_POLICY_INVALID
    assert any(f.startswith(field) for f in caught.value.fields)  # non-vacuous: names the field


@pytest.mark.parametrize(
    "text",
    [
        "retention:\n  logs: {max_age_days: SECRET-VALUE-123}\n",
        "retention:\n  scratch: {staging: SECRET-VALUE-123}\n",
        "retention:\n  records:\n    default: {keep: SECRET-VALUE-123}\n",
        "retention: [SECRET-VALUE-123\n",
        "- SECRET-VALUE-123\n",
    ],
)
def test_a_bad_value_error_names_fields_never_the_value(root: Path, text: str) -> None:
    _write(root, text)
    with pytest.raises(LibraryError) as caught:
        load_policy(root)
    err = caught.value
    assert err.code == LIBRARY_POLICY_INVALID
    assert "SECRET-VALUE-123" not in str(err) and "SECRET-VALUE-123" not in repr(err)
    assert "SECRET-VALUE-123" not in " ".join(err.fields)
    assert err.__cause__ is None and err.__context__ is None


def test_a_bool_or_text_number_is_not_coerced(root: Path) -> None:
    _write(root, "retention:\n  logs: {max_age_days: '30'}\n")
    with pytest.raises(LibraryError):
        load_policy(root)
    _write(root, "retention:\n  logs: {max_age_days: true}\n")
    with pytest.raises(LibraryError) as caught:
        load_policy(root)
    assert caught.value.fields == ("retention.logs.max_age_days",)


@pytest.mark.skipif(os.name != "posix", reason="POSIX symlinks")
def test_a_symlinked_policy_file_is_refused(root: Path, tmp_path: Path) -> None:
    real = tmp_path / "elsewhere.yaml"
    real.write_text("retention: {}\n", encoding="utf-8")
    (root / "library.yaml").symlink_to(real)
    with pytest.raises(LibraryError) as caught:
        load_policy(root)
    assert caught.value.code == LIBRARY_POLICY_INVALID
    assert caught.value.fields == ()


# -- review round 1 on #206, item 4: the one marker reader --------------------------------------


def test_the_policy_is_read_by_the_one_owned_yaml_reader(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from decoy.cli.io import _project
    from decoy.cli.library import _policy

    assert not hasattr(_policy, "read_small_file") and not hasattr(_policy, "yaml")
    calls: list[str] = []
    real = getattr(_project, "read_owned_yaml", None)

    def spy(path: Path, max_bytes: int) -> object:
        calls.append(Path(path).name)
        return real(path, max_bytes)  # type: ignore[misc]

    monkeypatch.setattr(_policy, "read_owned_yaml", spy, raising=False)
    _write(root, "retention: {}\n")
    load_policy(root)
    assert calls == ["library.yaml"]


@pytest.mark.skipif(not hasattr(os, "geteuid"), reason="POSIX owner check")
def test_a_policy_file_owned_by_another_user_is_refused(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The marker's owner rule (git `safe.directory`): a file someone else owns is not trusted."""
    _write(root, "retention: {}\n")
    real_uid = os.geteuid()
    monkeypatch.setattr(os, "geteuid", lambda: real_uid + 1)
    with pytest.raises(LibraryError) as caught:
        load_policy(root)
    assert caught.value.code == _errors.LIBRARY_POLICY_UNTRUSTED
    monkeypatch.undo()
    assert load_policy(root) == LibraryPolicy()  # control: owned by us, it reads
