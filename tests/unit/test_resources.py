"""AT-C3a: the resources resolver (flag, env, settings file, auto) and its strict readers."""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

from decoy import _resources
from decoy._resources import Resolved, ResourceError, resolve

SRC = Path(_resources.__file__).parent
GIB = 2**30


@pytest.fixture(autouse=True)
def _host(monkeypatch: pytest.MonkeyPatch) -> None:
    """A fixed 'host' so auto is deterministic: 3 GiB conservative budget, 6 CPUs."""
    monkeypatch.setattr(_resources, "_auto_memory", lambda: 3 * GIB)
    monkeypatch.setattr(_resources, "_auto_threads", lambda: 6)


def _settings(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "settings.toml"
    path.write_text(text, encoding="utf-8")
    return path


def _file(tmp_path: Path, memory: str = '"8GiB"', threads: str = "4") -> Path:
    return _settings(
        tmp_path,
        f'schema_version = "1.0"\n[resources]\nmax_memory = {memory}\nthreads = {threads}\n',
    )


def test_auto_everywhere(tmp_path: Path) -> None:
    got = resolve(env={}, settings=tmp_path / "missing.toml")
    assert got == Resolved(3 * GIB, 6, "auto", "auto")
    assert _resources.run_pipeline_kwargs(got) == {
        "native_threads": 6,
        "out_of_core_threads": 6,
        "out_of_core_budget_bytes": 3 * GIB,
    }


@pytest.mark.parametrize(
    ("flag", "env", "file", "source", "expected"),
    [
        ("1GiB", "2GiB", True, "flag", GIB),
        (None, "2GiB", True, "env", 2 * GIB),
        (None, None, True, "settings", 8 * GIB),
        (None, None, False, "auto", 3 * GIB),
        ("auto", "2GiB", True, "flag", 3 * GIB),
    ],
)
def test_memory_precedence(tmp_path, flag, env, file, source, expected) -> None:
    got = resolve(
        max_memory=flag,
        env={"DECOY_MAX_MEMORY": env} if env else {},
        settings=_file(tmp_path) if file else tmp_path / "none.toml",
    )
    assert (got.memory_bytes, got.memory_source) == (expected, source)


@pytest.mark.parametrize(
    ("flag", "env", "file", "source", "expected"),
    [
        ("2", "3", True, "flag", 2),
        (None, "3", True, "env", 3),
        (None, None, True, "settings", 4),
        (None, None, False, "auto", 6),
    ],
)
def test_threads_precedence(tmp_path, flag, env, file, source, expected) -> None:
    got = resolve(
        threads=flag,
        env={"DECOY_THREADS": env} if env else {},
        settings=_file(tmp_path) if file else tmp_path / "none.toml",
    )
    assert (got.threads, got.threads_source) == (expected, source)


def test_a_key_is_resolved_independently(tmp_path: Path) -> None:
    got = resolve(threads="2", env={}, settings=_file(tmp_path))
    assert (got.memory_source, got.threads_source) == ("settings", "flag")


def test_bad_settings_file_is_not_read_when_every_key_is_overridden(tmp_path: Path) -> None:
    bad = _settings(tmp_path, "not toml [")
    got = resolve(max_memory="1GiB", threads="2", env={}, settings=bad)
    assert (got.memory_bytes, got.threads) == (GIB, 2)


def test_empty_env_value_counts_as_unset(tmp_path: Path) -> None:
    got = resolve(env={"DECOY_THREADS": ""}, settings=tmp_path / "none.toml")
    assert got.threads_source == "auto"


@pytest.mark.parametrize(
    "text", ["-1", "0", "8gb ", "8GiB\n", "auto2", "8 GiB", "8GIB", "1e3", "", "08"]
)
def test_bad_size_text_is_refused_with_no_value(text: str) -> None:
    with pytest.raises(ResourceError) as err:
        resolve(max_memory=text, env={})
    assert (err.value.__cause__, err.value.__context__) == (None, None)
    assert str(err.value).startswith("--max-memory ")


def test_refusal_text_never_echoes_the_value() -> None:
    for kwargs in ({"max_memory": "canary-x9"}, {"threads": "canary-x9"}):
        with pytest.raises(ResourceError) as err:
            resolve(env={}, **kwargs)
        assert "canary" not in str(err.value)


@pytest.mark.parametrize("text", ["-1", "0", "true", "6\n", "auto2", "1.5", "70000", " 6", ""])
def test_bad_thread_text_is_refused(text: str) -> None:
    with pytest.raises(ResourceError) as err:
        resolve(threads=text, env={})
    assert (err.value.__cause__, err.value.__context__) == (None, None)


def test_env_error_names_the_variable() -> None:
    with pytest.raises(ResourceError, match=r"^DECOY_THREADS "):
        resolve(env={"DECOY_THREADS": "x"})


@pytest.mark.parametrize(
    ("text", "bytes_"),
    [("1", 1), ("512MiB", 512 * 2**20), ("2TB", 2 * 10**12), ("8GiB", 8 * GIB), ("1KB", 1000)],
)
def test_parse_size(text: str, bytes_: int) -> None:
    assert _resources.parse_size(text) == bytes_


@pytest.mark.parametrize(
    "body",
    [
        "schema_version = 1.0\n[resources]\nthreads = 2\n",  # number, not string
        'schema_version = "1"\n',
        'schema_version = "1.0\\n"\n',
        'schema_version = "2.0"\n',
        'schema_version = "0.9"\n',
        'schema_version = "1.0.1"\n',
        "[resources]\nthreads = 2\n",  # missing
        'schema_version = "1.0"\nresources = 3\n',
        'schema_version = "1.0"\n[resources]\nthreads = true\n',
        'schema_version = "1.0"\n[resources]\nthreads = "6"\n',
        'schema_version = "1.0"\n[resources]\nthreads = 0\n',
        'schema_version = "1.0"\n[resources]\nthreads = 1.5\n',
        'schema_version = "1.0"\n[resources]\nmax_memory = 8\n',
        'schema_version = "1.0"\n[resources]\nmax_memory = "8gb "\n',
        'schema_version = "1.0"\n[resources]\nmax_memory = true\n',
    ],
)
def test_strict_stored_types_and_versions(tmp_path: Path, body: str) -> None:
    with pytest.raises(ResourceError) as err:
        resolve(env={}, settings=_settings(tmp_path, body))
    assert (err.value.__cause__, err.value.__context__) == (None, None)
    assert str(err.value).startswith("settings.toml")


def test_unknown_minor_and_unknown_keys_are_accepted(tmp_path: Path) -> None:
    path = _settings(
        tmp_path,
        'schema_version = "1.7"\nfuture = 1\n[resources]\nthreads = 2\nextra = "x"\n[scan]\nml = true\n',
    )
    assert resolve(env={}, settings=path).threads == 2


def test_auto_literals_in_the_file(tmp_path: Path) -> None:
    got = resolve(env={}, settings=_file(tmp_path, '"auto"', '"auto"'))
    assert (got.memory_source, got.threads_source) == ("settings", "settings")
    assert (got.memory_bytes, got.threads) == (3 * GIB, 6)


def test_invalid_toml_and_binary_are_refused_without_chaining(tmp_path: Path) -> None:
    for payload in (b"x = [", b"\xff\xfe\x00", b"a" * 70000):
        path = tmp_path / "settings.toml"
        path.write_bytes(payload)
        with pytest.raises(ResourceError) as err:
            resolve(env={}, settings=path)
        assert (err.value.__cause__, err.value.__context__) == (None, None)


def test_auto_passes_the_engine_policy_bytes_not_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """M-C3a: CLI auto is an explicit byte value from the engine's conservative policy."""
    monkeypatch.undo()
    import decoy_engine

    monkeypatch.setattr(decoy_engine, "resolve_conservative_ooc_budget_bytes", lambda: 5 * GIB)
    monkeypatch.setattr(decoy_engine, "detect_usable_cpus", lambda: 3)
    got = resolve(env={}, settings=Path("/nonexistent/settings.toml"))
    assert _resources.run_pipeline_kwargs(got)["out_of_core_budget_bytes"] == 5 * GIB
    assert _resources.run_pipeline_kwargs(got)["out_of_core_threads"] == 3


def test_engine_detection_failure_is_a_coded_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.undo()
    import decoy_engine

    def boom() -> int:
        raise RuntimeError("secret-looking /path text")

    monkeypatch.setattr(decoy_engine, "detect_usable_cpus", boom)
    with pytest.raises(ResourceError) as err:
        resolve(max_memory="1GiB", env={}, settings=Path("/nonexistent/settings.toml"))
    assert "secret-looking" not in str(err.value)
    assert (err.value.__cause__, err.value.__context__) == (None, None)


def test_cli_never_owns_the_budget_floor_or_fraction() -> None:
    """No CLI module imports the engine's private floor or redoes its 25% arithmetic."""
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "_MIN_BUDGET_BYTES" not in text, path
        assert "_HOST_RAM_FRACTION" not in text, path
    tree = ast.parse((SRC / "_resources.py").read_text(encoding="utf-8"))
    consts = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)}
    assert 0.25 not in consts


def _atomic_sites(source: str) -> list[tuple[int, str]]:
    spec = importlib.util.spec_from_file_location(
        "_atomic_sentry", Path(__file__).parents[1] / "sentry" / "test_atomic_writer.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(module)
    return module.inline_sites(source)


def test_resources_module_has_no_inline_writer_and_a_seeded_one_is_seen() -> None:
    real = (SRC / "_resources.py").read_text(encoding="utf-8")
    assert _atomic_sites(real) == []
    seeded = real + "\nimport os\nos.replace('a', 'b')\n"
    assert _atomic_sites(seeded) != []
