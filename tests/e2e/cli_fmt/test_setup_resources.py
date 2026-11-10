"""AT-C3b: `decoy setup`, the settings file it writes, and the doctor rows."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from decoy import _resources
from decoy.__main__ import app

GIB = 2**30
runner = CliRunner()


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    monkeypatch.setenv("DECOY_HOME", str(home))
    monkeypatch.delenv("DECOY_MAX_MEMORY", raising=False)
    monkeypatch.delenv("DECOY_THREADS", raising=False)
    monkeypatch.setattr(_resources, "_auto_memory", lambda: 8 * GIB)
    monkeypatch.setattr(_resources, "_auto_threads", lambda: 6)
    return home


def test_yes_json_writes_versioned_settings_with_detected_values(_home: Path) -> None:
    result = runner.invoke(app, ["setup", "--yes", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["sections"] == {"resources": {"max_memory": "8GiB", "threads": 6}}
    data = json.loads((_home / "settings.json").read_text(encoding="utf-8"))
    assert data == {"schema_version": "1.0", "resources": {"max_memory": "8GiB", "threads": 6}}
    assert (_home / "settings.json").stat().st_mode & 0o077 == 0
    assert list(_home.glob(".*.tmp")) == []


def test_write_goes_through_the_atomic_writer(monkeypatch: pytest.MonkeyPatch, _home: Path) -> None:
    calls: list[tuple[Path, str, object]] = []
    real = _resources.write_atomic

    def spy(directory, name, data, mode, **kw):
        calls.append((directory, name, mode))
        return real(directory, name, data, mode, **kw)

    monkeypatch.setattr(_resources, "write_atomic", spy)
    assert runner.invoke(app, ["setup", "--yes"]).exit_code == 0
    assert calls == [(_home, "settings.json", _resources.WriteMode.REPLACE)]


def test_off_a_terminal_without_yes_exits_1_and_writes_nothing(_home: Path) -> None:
    result = runner.invoke(app, ["setup"])
    assert result.exit_code == 1
    assert not (_home / "settings.json").exists()


def test_setup_keeps_a_valid_stored_value_as_the_default(_home: Path) -> None:
    _home.mkdir()
    (_home / "settings.json").write_text(
        '{"schema_version": "1.0", "resources": {"max_memory": "2GiB", "threads": "auto"}}'
    )
    assert runner.invoke(app, ["setup", "--yes"]).exit_code == 0
    data = json.loads((_home / "settings.json").read_text())
    assert data["resources"] == {"max_memory": "2GiB", "threads": "auto"}


def test_setup_replaces_an_unusable_file(_home: Path) -> None:
    _home.mkdir()
    (_home / "settings.json").write_text("not json [")
    assert runner.invoke(app, ["setup", "--yes"]).exit_code == 0
    assert _resources.read_settings() == {"max_memory": 8 * GIB, "threads": 6}


def test_setup_section_order_is_fixed() -> None:
    from decoy.cli.setup._sections import SECTIONS

    assert [s.name for s in SECTIONS] == ["resources"]


def test_doctor_shows_each_value_and_its_source(
    _home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DECOY_THREADS", "3")
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0, result.output
    rows = {c["name"]: c["note"] for c in json.loads(result.stdout)["checks"]}
    assert rows["max-memory"] == "8GiB (auto)"
    assert rows["threads"] == "3 (env)"


def test_doctor_warns_on_an_unusable_settings_file(_home: Path) -> None:
    _home.mkdir()
    (_home / "settings.json").write_text('{"schema_version": "9.0"}')
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0
    row = next(c for c in json.loads(result.stdout)["checks"] if c["name"] == "resources")
    assert row["status"] == "warn"
    assert "9.0" not in row["note"]


def test_run_rejects_a_bad_flag_with_usage_exit(tmp_path: Path) -> None:
    cfg = tmp_path / "p.yaml"
    cfg.write_text("version: 1\n")
    result = runner.invoke(app, ["run", str(cfg), "--threads", "0"])
    assert result.exit_code == 1


def test_setup_keeps_other_sections_unknown_keys_and_a_higher_minor(_home: Path) -> None:
    _home.mkdir()
    before = {
        "schema_version": "1.7",
        "future": {"a": [1, 2]},
        "scan": {"ml": True},
        "resources": {"max_memory": "2GiB", "threads": 3, "extra": "x"},
    }
    (_home / "settings.json").write_text(json.dumps(before))
    assert runner.invoke(app, ["setup", "--yes"]).exit_code == 0
    after = json.loads((_home / "settings.json").read_text())
    assert after == before


def test_setup_says_when_it_replaces_an_unusable_file(_home: Path) -> None:
    _home.mkdir()
    (_home / "settings.json").write_text("not json [")
    payload = json.loads(runner.invoke(app, ["setup", "--yes", "--json"]).stdout)
    assert payload["replaced_unusable_file"] is True
    result = runner.invoke(app, ["setup", "--yes"])
    assert "replaced" not in result.stdout


@pytest.mark.parametrize(("mode", "warns"), [(0o666, True), (0o620, True), (0o600, False)])
def test_doctor_warns_on_a_writable_settings_file(_home: Path, mode: int, warns: bool) -> None:
    _home.mkdir()
    path = _home / "settings.json"
    path.write_text('{"schema_version": "1.0"}')
    path.chmod(mode)
    rows = {
        c["name"]: c for c in json.loads(runner.invoke(app, ["doctor", "--json"]).stdout)["checks"]
    }
    assert ("settings-file" in rows) is warns
    if warns:
        assert rows["settings-file"]["status"] == "warn"
        assert str(_home) not in rows["settings-file"]["note"]


@pytest.mark.parametrize(
    "body",
    ['{"schema_version": "2.0", "keep": 1}', '{"schema_version": "1.0", "resources": 3}'],
)
def test_setup_refuses_a_readable_document_it_does_not_understand(_home: Path, body: str) -> None:
    _home.mkdir()
    (_home / "settings.json").write_text(body)
    result = runner.invoke(app, ["setup", "--yes"])
    assert result.exit_code == 1
    assert (_home / "settings.json").read_text() == body
    assert "2.0" not in result.output


@pytest.mark.parametrize("body", ["not json [", "[1, 2]", '{"a": 1, "a": 2}'])
def test_setup_replaces_only_a_truly_unusable_file(_home: Path, body: str) -> None:
    _home.mkdir()
    (_home / "settings.json").write_text(body)
    assert runner.invoke(app, ["setup", "--yes"]).exit_code == 0
    assert json.loads((_home / "settings.json").read_text())["schema_version"] == "1.0"


def test_setup_refuses_at_once_while_another_writer_holds_the_lock(_home: Path) -> None:
    from decoy.cli.setup import SETTINGS_LOCK
    from decoy.distribution import lock

    _home.mkdir()
    path = _home / "settings.json"
    path.write_text('{"schema_version": "1.0", "keep": 1}')
    with lock.exclusive(_home, SETTINGS_LOCK):
        result = runner.invoke(app, ["setup", "--yes"])
    assert result.exit_code == 1
    assert "re-run" in result.output
    assert path.read_text() == '{"schema_version": "1.0", "keep": 1}'
    assert runner.invoke(app, ["setup", "--yes"]).exit_code == 0


def test_a_change_made_while_setup_prompts_is_merged_not_lost(
    _home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from decoy.cli.setup._resources import ResourcesSection

    _home.mkdir()
    path = _home / "settings.json"
    path.write_text('{"schema_version": "1.0"}')
    real = ResourcesSection.propose

    def propose(self, stored):
        out = real(self, stored)
        path.write_text('{"schema_version": "1.0", "added_meanwhile": true}')
        return out

    monkeypatch.setattr(ResourcesSection, "propose", propose)
    assert runner.invoke(app, ["setup", "--yes"]).exit_code == 0
    assert json.loads(path.read_text())["added_meanwhile"] is True


def test_setup_reports_the_version_it_wrote(_home: Path) -> None:
    _home.mkdir()
    (_home / "settings.json").write_text('{"schema_version": "1.7"}')
    payload = json.loads(runner.invoke(app, ["setup", "--yes", "--json"]).stdout)
    assert payload["schema_version"] == "1.7"
    assert json.loads((_home / "settings.json").read_text())["schema_version"] == "1.7"
