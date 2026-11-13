"""R1-c: the CycloneDX SBOM generator for the CLI bundle (scripts/release/sbom.sh).

Runs the real script on a tiny fixture pin list (tests/fixtures/sbom_runtime) and
checks the output against the CycloneDX JSON schema, against the pin list
(completeness), for byte-identical reruns, and for leaks of paths or environment
values. Needs ``uv`` and network access to PyPI on first use (the pinned
``cyclonedx-py`` runs from a throwaway venv built from sbom-tool-requirements.txt).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

_REPO_ROOT = Path(__file__).parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "release" / "sbom.sh"
_FIXTURE = _REPO_ROOT / "tests" / "fixtures" / "sbom_runtime"
_FIXTURE_PINS = _FIXTURE / "requirements-runtime.txt"
_RELEASE_PINS = _REPO_ROOT / "requirements-certified.txt"
_DEV_LOCK = _REPO_ROOT / "requirements-dev.lock"

_PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==(\S+)")
_HASH = re.compile(r"--hash=sha256:([0-9a-f]{64})")


def _require_uv() -> None:
    # Fail, do not skip: a gate that silently stops running is worse than a red one.
    assert shutil.which("uv"), "uv is required on PATH to run the SBOM tests"


_TOOL_REQUIREMENTS = _REPO_ROOT / "scripts" / "release" / "sbom-tool-requirements.txt"


def _pin(name: str) -> str:
    # The hashed tool environment file is the single source of truth for the tool pins.
    m = re.search(rf"^{name}==(\S+)", _TOOL_REQUIREMENTS.read_text(), re.M)
    assert m, f"{name} pin not found in {_TOOL_REQUIREMENTS}"
    return m.group(1)


def _script_copy(tmp_path: Path) -> Path:
    """A throwaway copy of scripts/release (+ the files the default input needs)."""
    root = tmp_path / "repo-copy"
    shutil.copytree(_SCRIPT.parent, root / "scripts" / "release")
    for name in ("requirements-certified.txt", "pyproject.toml"):
        shutil.copy(_REPO_ROOT / name, root / name)
    return root / "scripts" / "release" / "sbom.sh"


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _run(
    pins: Path,
    out: Path,
    env_extra: dict[str, str] | None = None,
    cwd: Path | None = None,
    script: Path = _SCRIPT,
):
    _require_uv()
    return subprocess.run(
        ["bash", str(script), str(pins), str(out)],
        capture_output=True,
        text=True,
        env={**os.environ, **(env_extra or {})},
        cwd=cwd,
        check=False,
    )


def _generate(tmp_path: Path, name: str = "sbom.cdx.json", **kw) -> Path:
    out = tmp_path / name
    r = _run(_FIXTURE_PINS, out, **kw)
    assert r.returncode == 0, r.stderr
    return out


def _pins(path: Path) -> dict[tuple[str, str], set[str]]:
    """(name, version) -> sha256 set, read straight from a requirements-format pin list."""
    out: dict[tuple[str, str], set[str]] = {}
    current: tuple[str, str] | None = None
    for line in path.read_text().splitlines():
        m = _PIN.match(line)
        if m:
            current = (_norm(m.group(1)), m.group(2))
            out.setdefault(current, set())
        if current:
            out[current].update(_HASH.findall(line))
    return out


def _sbom_components(sbom: dict) -> dict[tuple[str, str], set[str]]:
    comps: dict[tuple[str, str], set[str]] = {}
    for c in sbom["components"]:
        hashes = {h["content"] for h in c.get("hashes", [])}
        for ref in c.get("externalReferences", []):
            hashes |= {h["content"] for h in ref.get("hashes", [])}
        comps.setdefault((_norm(c["name"]), c["version"]), set()).update(hashes)
    return comps


def missing_from_sbom(pins: Path, sbom: dict) -> list[tuple[str, str]]:
    """Pinned runtime packages with no component in the SBOM."""
    have = _sbom_components(sbom)
    return sorted(k for k in _pins(pins) if k not in have)


def test_sbom_script_exists():
    assert _SCRIPT.is_file(), "scripts/release/sbom.sh is missing"


def test_sbom_validates_against_cyclonedx_json_schema(tmp_path):
    out = _generate(tmp_path)
    doc = json.loads(out.read_text())
    assert doc["bomFormat"] == "CycloneDX"
    assert tuple(int(x) for x in doc["specVersion"].split(".")) >= (1, 5)
    # The script's --validate mode: the pinned library's bundled strict JSON schema, in
    # the same hashed tool environment, independent of the generator's own --validate step.
    r = subprocess.run(
        ["bash", str(_SCRIPT), "--validate", str(out)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0 and "VALID" in r.stdout, r.stdout + r.stderr
    assert _pin("cyclonedx-bom") == "7.6.0"


def test_every_pinned_package_is_in_the_sbom(tmp_path):
    sbom = json.loads(_generate(tmp_path).read_text())
    assert missing_from_sbom(_FIXTURE_PINS, sbom) == []
    assert set(_sbom_components(sbom)) == set(_pins(_FIXTURE_PINS))
    assert ("numpy", "2.2.6") in _sbom_components(sbom)


def test_completeness_check_reports_a_dropped_package(tmp_path):
    sbom = json.loads(_generate(tmp_path).read_text())
    sbom["components"] = [c for c in sbom["components"] if c["name"] != "six"]
    assert missing_from_sbom(_FIXTURE_PINS, sbom) == [("six", "1.17.0")]


def test_hashes_present_only_where_the_pin_list_has_them(tmp_path):
    have = _sbom_components(json.loads(_generate(tmp_path).read_text()))
    expect = _pins(_FIXTURE_PINS)
    assert expect[("six", "1.17.0")], "fixture must carry hashes for six"
    assert expect[("python-dateutil", "2.9.0.post0")] == set()
    assert have == expect


def test_component_licenses_are_not_invented(tmp_path):
    sbom = json.loads(_generate(tmp_path).read_text())
    assert all("licenses" not in c for c in sbom["components"])
    assert sbom["metadata"]["component"]["name"] == "decoy-cli"
    assert sbom["metadata"]["component"]["licenses"]


def test_two_runs_are_byte_identical_even_with_source_date_epoch(tmp_path):
    a = _generate(tmp_path, "a.json", env_extra={"SOURCE_DATE_EPOCH": "1"})
    b = _generate(tmp_path, "b.json", env_extra={"SOURCE_DATE_EPOCH": "1700000000"})
    assert a.read_bytes() == b.read_bytes()
    doc = json.loads(a.read_text())
    assert "serialNumber" not in doc
    assert "timestamp" not in doc["metadata"]


def test_output_contains_no_paths_or_environment_values(tmp_path):
    workdir = tmp_path / "canary-workdir-7731"
    workdir.mkdir()
    canary = "CANARY_ENV_VALUE_9f3a"
    out = tmp_path / "canary-outdir-5520" / "sbom.cdx.json"
    out.parent.mkdir()
    r = _run(
        _FIXTURE_PINS,
        out,
        env_extra={"DECOY_MASK_SECRET": canary, "AWS_SECRET_ACCESS_KEY": canary, "USER": canary},
        cwd=workdir,
    )
    assert r.returncode == 0, r.stderr
    text = out.read_text()
    for needle in (
        canary,
        "canary-workdir",
        "canary-outdir",
        str(tmp_path),
        str(_REPO_ROOT),
        "file://",
    ):
        assert needle not in text
    assert not re.search(r"(?<![\w.:])/(home|tmp|root|Users|var)/", text)


def test_missing_input_fails_without_writing_output(tmp_path):
    out = tmp_path / "sbom.cdx.json"
    r = _run(tmp_path / "nope.txt", out)
    assert r.returncode != 0
    assert "pin list not found" in r.stderr
    assert not out.exists()


def test_error_messages_do_not_echo_the_callers_path(tmp_path):
    secret_dir = tmp_path / "canary-private-dir-4417"
    secret_dir.mkdir()
    out = tmp_path / "sbom.cdx.json"
    r = _run(secret_dir / "missing.txt", out)
    assert r.returncode != 0
    assert "canary-private-dir" not in r.stderr
    bad = secret_dir / "bad.txt"
    bad.write_text("-e ./x\n")
    r = _run(bad, out)
    assert r.returncode != 0
    assert "canary-private-dir" not in r.stderr


CANARY = "CANARY_COMMENT_VALUE_c41e"

_BAD_PIN_FILES = {
    "index-url": "six==1.17.0\n--index-url https://corp-index.internal.example/simple\n",
    "file-url": "six==1.17.0\nsix @ file:///srv/vendored/six\n",
    "git-url": "decoy-engine @ git+https://example.invalid/decoy-engine@abc\n",
    "editable": "six==1.17.0\n-e ./local\n",
    "include": "six==1.17.0\n-r other.txt\n",
    "comment-after-marker": f"six==1.17.0 ; python_version >= '3.0' # {CANARY} https://internal.example/x\n",
    "comment-after-pin": f"six==1.17.0 # {CANARY}\n",
    "option-after-marker": f"six==1.17.0 ; python_version >= '3.0' --index-url https://{CANARY}.example/s\n",
    "version-token-smuggling": f"six==1.17.0,--no-binary={CANARY}\n",
    "version-specifier-list": f"six==1.17.0,!=1.0.{CANARY}\n",
    "orphan-hash": f"six==1.17.0\n    --hash=sha256:{'ab' * 32}\n",
    "hash-first": f"    --hash=sha256:{'ab' * 32}\nsix==1.17.0\n",
    "dangling-continuation": "six==1.17.0 \\\n",
    "continuation-then-blank": "six==1.17.0 \\\n\nnumpy==2.2.6\n",
    "continuation-then-pin": "six==1.17.0 \\\nnumpy==2.2.6\n",
    "hash-trailing-continuation": f"six==1.17.0 \\\n    --hash=sha256:{'ab' * 32} \\\n",
    "malformed-hash": "six==1.17.0 \\\n    --hash=sha256:xyz\n",
    "tab-indented-hash": f"six==1.17.0 \\\n\t--hash=sha256:{'ab' * 32}\n",
}


@pytest.mark.parametrize("content", list(_BAD_PIN_FILES.values()), ids=list(_BAD_PIN_FILES))
def test_non_pin_lines_fail_closed(tmp_path, content):
    pins = tmp_path / "requirements-runtime.txt"
    pins.write_text(content)
    out = tmp_path / "sbom.cdx.json"
    r = _run(pins, out)
    assert r.returncode != 0
    assert "non-public source or unsupported requirement" in r.stderr
    assert CANARY not in r.stderr
    assert not out.exists()


def test_whole_line_comments_are_allowed_but_never_reach_the_output(tmp_path):
    """Positive control for the grammar, and a canary that a comment never leaks."""
    pins = tmp_path / "requirements-runtime.txt"
    pins.write_text(
        f"# {CANARY} header comment with https://internal.example/x\n\n"
        f"six==1.17.0 \\\n    --hash=sha256:{'ab' * 32}\n"
        f"# {CANARY} between pins\n"
        "numpy==2.2.6 ; python_full_version < '3.11'\n"
    )
    out = tmp_path / "sbom.cdx.json"
    r = _run(pins, out)
    assert r.returncode == 0, r.stderr
    assert CANARY not in out.read_text()
    assert "internal.example" not in out.read_text()
    assert set(_sbom_components(json.loads(out.read_text()))) == {
        ("six", "1.17.0"),
        ("numpy", "2.2.6"),
    }


def test_a_relative_path_starting_with_a_dash_is_a_file_not_an_option(tmp_path):
    (tmp_path / "-pins.txt").write_text("six==1.17.0\n")
    r = _run(Path("-pins.txt"), Path("-out.json"), cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert set(_sbom_components(json.loads((tmp_path / "-out.json").read_text()))) == {
        ("six", "1.17.0")
    }


def test_dev_profile_lock_is_refused(tmp_path):
    """requirements-dev.lock is the dev profile (it carries the engine as a git URL): not an input."""
    out = tmp_path / "sbom.cdx.json"
    r = _run(_DEV_LOCK, out)
    assert r.returncode != 0
    assert "non-public source or unsupported requirement" in r.stderr
    assert not out.exists()


def test_no_arguments_sboms_the_certified_runtime_pin_list(tmp_path):
    _require_uv()
    r = subprocess.run(
        ["bash", str(_SCRIPT)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=False,
    )
    assert r.returncode == 0, r.stderr
    sbom = json.loads((tmp_path / "sbom.cdx.json").read_text())
    assert missing_from_sbom(_RELEASE_PINS, sbom) == []
    assert len(_pins(_RELEASE_PINS)) == 67
    assert set(_sbom_components(sbom)) == set(_pins(_RELEASE_PINS))
    assert sbom["metadata"]["component"]["name"] == "decoy-cli"
    # No dev tooling in the runtime SBOM.
    assert not {"pytest", "ruff", "mypy"} & {c["name"] for c in sbom["components"]}


# --- hashed tool environment ------------------------------------------------


def test_tool_requirements_file_is_fully_hashed_and_pinned():
    text = _TOOL_REQUIREMENTS.read_text()
    assert {"cyclonedx-bom", "cyclonedx-python-lib"} <= set(
        re.findall(r"^([A-Za-z0-9._-]+)==", text, re.M)
    )
    blocks = re.split(r"(?m)^(?=[A-Za-z0-9._-]+==)", text)[1:]
    assert blocks
    assert all("--hash=sha256:" in b for b in blocks)


def test_missing_tool_requirements_fails_without_writing_output(tmp_path):
    script = _script_copy(tmp_path)
    (script.parent / "sbom-tool-requirements.txt").unlink()
    out = tmp_path / "sbom.cdx.json"
    r = _run(_FIXTURE_PINS, out, script=script)
    assert r.returncode != 0
    assert "tool requirements file not found" in r.stderr
    assert not out.exists()


def _corrupt_arrow(script: Path, how: str) -> None:
    req = script.parent / "sbom-tool-requirements.txt"
    text = req.read_text()
    i, j = text.index("arrow=="), text.index("\nattrs==")
    if how == "mismatch":  # every hash of one package, since one good hash would suffice
        block = re.sub(r"sha256:[0-9a-f]{4}", "sha256:0000", text[i:j])
    else:  # strip the hashes from one package
        block = re.sub(r" \\\n\s+--hash=sha256:[0-9a-f]{64}", "", text[i:j])
    req.write_text(text[:i] + block + text[j:])


@pytest.mark.parametrize("how", ["mismatch", "unhashed-entry"])
def test_tool_environment_hashes_are_enforced(tmp_path, how):
    script = _script_copy(tmp_path)
    _corrupt_arrow(script, "mismatch" if how == "mismatch" else "strip")
    out = tmp_path / "sbom.cdx.json"
    r = _run(_FIXTURE_PINS, out, script=script)
    assert r.returncode != 0
    assert "tool environment install failed" in r.stderr
    assert not out.exists()


# --- names, purls, documented commands -----------------------------------------


def test_completeness_check_normalizes_package_names(tmp_path):
    assert _norm("typing_extensions") == _norm("Typing-Extensions") == "typing-extensions"
    pins = tmp_path / "p.txt"
    pins.write_text("typing_extensions==4.0.0\n")
    sbom = {"components": [{"name": "typing-extensions", "version": "4.0.0"}]}
    assert missing_from_sbom(pins, sbom) == []
    assert missing_from_sbom(pins, {"components": []}) == [("typing-extensions", "4.0.0")]


def test_every_component_has_a_pypi_purl_matching_its_name_and_version(tmp_path):
    sbom = json.loads(_generate(tmp_path).read_text())
    assert sbom["components"]
    for c in sbom["components"]:
        assert c["purl"] == f"pkg:pypi/{_norm(c['name'])}@{c['version']}"


def test_documented_commands_run(tmp_path):
    """Every shell command in docs/release/sbom.md works from a repo-shaped directory."""
    _require_uv()
    _script_copy(tmp_path)
    root = tmp_path / "repo-copy"
    blocks = re.findall(
        r"```bash\n(.*?)```", (_REPO_ROOT / "docs" / "release" / "sbom.md").read_text(), re.S
    )
    cmds = [ln.split("#")[0].strip() for b in blocks for ln in b.splitlines() if ln.strip()]
    cmds = [c for c in cmds if c]
    assert cmds, "no documented commands found"
    for cmd in cmds:
        assert cmd.startswith(("scripts/release/sbom.sh", "scripts/release/sbom-tool-lock.sh")), (
            f"undocumented tool in docs: {cmd}"
        )
        r = subprocess.run(cmd, shell=True, cwd=root, capture_output=True, text=True, check=False)
        assert r.returncode == 0, f"{cmd}: {r.stderr}"
    assert (root / "sbom.cdx.json").is_file()


# --- round 2: run-time isolation (class A) -----------------------------------

_SHA = "ab" * 32


def _shadow_dir(tmp_path: Path) -> Path:
    shadow = tmp_path / "shadow"
    (shadow / "cyclonedx_py").mkdir(parents=True)
    (shadow / "cyclonedx_py" / "__init__.py").write_text('raise SystemExit("SHADOWED_TOOL")\n')
    return shadow


def test_pythonpath_cannot_shadow_the_hashed_tool(tmp_path):
    out = tmp_path / "sbom.cdx.json"
    r = _run(_FIXTURE_PINS, out, env_extra={"PYTHONPATH": str(_shadow_dir(tmp_path))})
    assert r.returncode == 0, r.stderr
    assert "SHADOWED_TOOL" not in r.stderr
    assert out.is_file()


def _canary_uv_config(tmp_path: Path) -> dict[str, str]:
    """A user uv.toml and a cwd uv.toml that both point uv at an unreachable index."""
    cfg = '[pip]\nindex-url = "https://canary-index.invalid/simple"\n'
    xdg = tmp_path / "xdg"
    (xdg / "uv").mkdir(parents=True)
    (xdg / "uv" / "uv.toml").write_text(cfg)
    (tmp_path / "uv.toml").write_text(cfg)
    return {"XDG_CONFIG_HOME": str(xdg)}


def test_ambient_uv_config_files_cannot_change_the_tool_index(tmp_path):
    out = tmp_path / "sbom.cdx.json"
    r = _run(_FIXTURE_PINS, out, env_extra=_canary_uv_config(tmp_path), cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert out.is_file()


@pytest.mark.parametrize("var", ["UV_INDEX_URL", "UV_DEFAULT_INDEX", "UV_EXTRA_INDEX_URL"])
def test_ambient_uv_environment_cannot_change_the_tool_index(tmp_path, var):
    out = tmp_path / "sbom.cdx.json"
    r = _run(_FIXTURE_PINS, out, env_extra={var: "https://canary-index.invalid/simple"})
    assert r.returncode == 0, r.stderr
    assert out.is_file()


def _uv_shim(tmp_path: Path, venv_python: str) -> dict[str, str]:
    """PATH shim: `uv venv` gets a different interpreter, everything else is real uv."""
    real_uv = shutil.which("uv")
    assert real_uv
    shim_dir = tmp_path / "uv-shim"
    shim_dir.mkdir()
    shim = shim_dir / "uv"
    shim.write_text(
        "#!/usr/bin/env bash\n"
        'if [ "$1" = venv ]; then\n'
        "  args=()\n"
        '  for a in "$@"; do\n'
        f'    if [ "${{prev:-}}" = --python ]; then a={venv_python}; fi\n'
        '    args+=("$a"); prev=$a\n'
        "  done\n"
        f'  exec {real_uv} "${{args[@]}}"\n'
        "fi\n"
        f'exec {real_uv} "$@"\n'
    )
    shim.chmod(0o755)
    return {"PATH": f"{shim_dir}{os.pathsep}{os.environ['PATH']}"}


def test_tool_interpreter_other_than_the_locked_minor_is_refused(tmp_path):
    out = tmp_path / "sbom.cdx.json"
    r = _run(_FIXTURE_PINS, out, env_extra=_uv_shim(tmp_path, "3.13"))
    assert r.returncode != 0
    assert "tool interpreter is not CPython 3.12" in r.stderr
    assert not out.exists()


# docopt 0.6.2 is published as an sdist only.
_SDIST_ONLY = (
    "docopt==0.6.2 \\\n"
    "    --hash=sha256:49b3a825280bd66b3aa83585ef59c4a8c82f2c8a522dbe754a8bc8d08c85c491\n"
)


def test_tool_install_never_builds_from_source(tmp_path):
    script = _script_copy(tmp_path)
    req = script.parent / "sbom-tool-requirements.txt"
    req.write_text(req.read_text() + _SDIST_ONLY)
    out = tmp_path / "sbom.cdx.json"
    r = _run(_FIXTURE_PINS, out, script=script)
    assert r.returncode != 0
    assert "tool environment install failed" in r.stderr
    assert not out.exists()


_BAD_TOOL_LINES = {
    "index-url": "--index-url https://canary-index.invalid/simple\n",
    "extra-index-url": "--extra-index-url https://canary-index.invalid/simple\n",
    "find-links": "--find-links ./wheels\n",
    "trusted-host": "--trusted-host canary-index.invalid\n",
    "direct-url": f"six @ https://canary-index.invalid/six.whl \\\n    --hash=sha256:{_SHA}\n",
    "path": f"./vendored/six \\\n    --hash=sha256:{_SHA}\n",
    "unhashed-pin": "six==1.17.0\n",
    "non-pep440-version": f"six==1..0 \\\n    --hash=sha256:{_SHA}\n",
    "cr-in-comment": "# via\rsix==1.17.0\n",
}


@pytest.mark.parametrize("line", list(_BAD_TOOL_LINES.values()), ids=list(_BAD_TOOL_LINES))
def test_tool_requirements_grammar_is_checked_before_install(tmp_path, line):
    script = _script_copy(tmp_path)
    req = script.parent / "sbom-tool-requirements.txt"
    req.write_bytes((req.read_text() + line).encode())
    out = tmp_path / "sbom.cdx.json"
    r = _run(_FIXTURE_PINS, out, script=script)
    assert r.returncode != 0
    assert "sbom-tool-requirements.txt is not hashed pins only" in r.stderr
    assert "canary-index" not in r.stderr
    assert not out.exists()


def _lock_script_copy(tmp_path: Path) -> Path:
    return _script_copy(tmp_path).parent / "sbom-tool-lock.sh"


def _run_lock(script: Path, env_extra: dict[str, str] | None = None, cwd: Path | None = None):
    _require_uv()
    return subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
        env={**os.environ, **(env_extra or {})},
        cwd=cwd,
        check=False,
    )


def test_tool_lock_ignores_ambient_uv_config_and_environment(tmp_path):
    script = _lock_script_copy(tmp_path)
    env = {**_canary_uv_config(tmp_path), "UV_INDEX_URL": "https://canary-index.invalid/simple"}
    r = _run_lock(script, env_extra=env, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert (script.parent / "sbom-tool-requirements.txt").read_bytes() == (
        _TOOL_REQUIREMENTS.read_bytes()
    )


def test_tool_lock_refuses_a_dependency_without_wheels(tmp_path):
    script = _lock_script_copy(tmp_path)
    req_in = script.parent / "sbom-tool-requirements.in"
    req_in.write_text(req_in.read_text() + "docopt==0.6.2\n")
    r = _run_lock(script)
    assert r.returncode != 0
    assert "docopt" not in (script.parent / "sbom-tool-requirements.txt").read_text()


def test_cdpath_does_not_redirect_or_pollute_the_script_directory(tmp_path):
    decoy = tmp_path / "decoy-tree"
    (decoy / "scripts" / "release").mkdir(parents=True)
    out = tmp_path / "sbom.cdx.json"
    r = subprocess.run(
        ["bash", "scripts/release/sbom.sh", str(_FIXTURE_PINS), str(out)],
        capture_output=True,
        text=True,
        env={**os.environ, "CDPATH": str(decoy)},
        cwd=_REPO_ROOT,
        check=False,
    )
    assert r.returncode == 0, r.stderr
    assert out.is_file()


# --- round 2: arguments and project metadata ----------------------------------


def test_extra_positional_arguments_are_refused(tmp_path):
    _require_uv()
    out = tmp_path / "sbom.cdx.json"
    r = subprocess.run(
        ["bash", str(_SCRIPT), str(_FIXTURE_PINS), str(out), "surplus"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode != 0
    assert "usage:" in r.stderr
    assert not out.exists()


@pytest.mark.parametrize("extra", [[], ["a.json", "b.json"]], ids=["no-file", "two-files"])
def test_validate_needs_exactly_one_file(extra):
    _require_uv()
    r = subprocess.run(
        ["bash", str(_SCRIPT), "--validate", *extra],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode != 0
    assert "usage:" in r.stderr


def test_root_component_comes_from_the_repo_root_pyproject(tmp_path):
    sbom = json.loads(_generate(tmp_path).read_text())
    assert sbom["metadata"]["component"]["name"] == "decoy-cli"
    assert (
        sbom["metadata"]["component"]["version"]
        == tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text())["project"]["version"]
    )


@pytest.mark.parametrize("how", ["missing", "no-version", "no-name"])
def test_missing_project_metadata_fails_closed(tmp_path, how):
    script = _script_copy(tmp_path)
    pyproject = tmp_path / "repo-copy" / "pyproject.toml"
    if how == "missing":
        pyproject.unlink()
    else:
        key = "version" if how == "no-version" else "name"
        text = pyproject.read_text()
        mutated = re.sub(rf'(?m)^{key} = "[^"]*"\n', "", text, count=1)
        assert mutated != text
        pyproject.write_text(mutated)
    out = tmp_path / "sbom.cdx.json"
    r = _run(_FIXTURE_PINS, out, script=script)
    assert r.returncode != 0
    assert "project metadata" in r.stderr
    assert not out.exists()


# --- round 2: checker versus parser (class B) ----------------------------------

_GRAMMAR = "non-public source or unsupported requirement"
# Every separator str.splitlines() honours beyond "\n", plus non-printable / non-ASCII text.
_SPLITLINES = ["\r", "\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", "\u2028", "\u2029"]


def _refused(tmp_path: Path, content: str | bytes, needle: str = _GRAMMAR):
    pins = tmp_path / "requirements-runtime.txt"
    pins.write_bytes(content if isinstance(content, bytes) else content.encode())
    out = tmp_path / "sbom.cdx.json"
    r = _run(pins, out)
    assert r.returncode != 0, "accepted"
    assert needle in r.stderr, r.stderr
    assert CANARY not in r.stderr
    assert not out.exists()


@pytest.mark.parametrize("sep", _SPLITLINES, ids=[f"U+{ord(s):04X}" for s in _SPLITLINES])
def test_splitlines_separators_in_a_comment_are_refused(tmp_path, sep):
    # The parser splits here, so the "comment" would smuggle in a numpy pin.
    _refused(tmp_path, f"# {CANARY}{sep}numpy==2.2.6\nsix==1.17.0\n")


@pytest.mark.parametrize(
    "content",
    [
        "six==1.17.0\r\n",
        f"# caf\u00e9 {CANARY}\nsix==1.17.0\n",
        f"#\t{CANARY}\nsix==1.17.0\n",
        b"\xef\xbb\xbfsix==1.17.0\n",
    ],
    ids=["crlf", "non-ascii-comment", "tab-in-comment", "utf8-bom"],
)
def test_non_printable_ascii_text_is_refused(tmp_path, content):
    _refused(tmp_path, content)


@pytest.mark.parametrize(
    "line",
    ["six==1..0", "six==1.17.0-", "six==1.17.0_post1", "six==.1", "six==1.0+Local"],
)
def test_versions_must_be_canonical_pep440(tmp_path, line):
    _refused(tmp_path, f"{line}\n")


@pytest.mark.parametrize(
    "line",
    [
        "six==1.17.0 ; python_version >>= '3.0'",
        "six==1.17.0 ; platform_cpu == 'x86'",
        "six==1.17.0 ; (python_version >= '3.0'",
    ],
    ids=["bad-operator", "unknown-variable", "unbalanced"],
)
def test_pins_the_requirement_parser_rejects_are_refused(tmp_path, line):
    _refused(tmp_path, f"{line}\n")


def test_a_parser_side_drop_is_a_hard_failure(tmp_path):
    # Valid ASCII and canonical PEP 440 to the checker, but the parser honours the coding
    # declaration and decodes "+aaaaaaaa" as UTF-7, so it drops the pin.
    _refused(
        tmp_path,
        "# -*- coding: utf-7 -*-\nsix==1.17.0+aaaaaaaa\n",
        needle="SBOM does not match the pin list",
    )


def test_an_empty_pin_list_is_refused(tmp_path):
    _refused(tmp_path, f"# {CANARY} only comments\n\n", needle="no pins")


@pytest.mark.parametrize(
    "content",
    [
        "six==1.17.0\nsix==1.17.0\n",
        "numpy==2.2.6 ; python_full_version < '3.11'\n"
        "numpy==2.5.0 ; python_full_version >= '3.12'\n",
        "typing_extensions==4.0.0\nTyping-Extensions==4.0.0\n",
    ],
    ids=["duplicate", "multi-version", "pep503-duplicate"],
)
def test_duplicate_or_multi_version_pins_are_refused(tmp_path, content):
    _refused(tmp_path, content, needle="duplicate or multi-version pin")


def test_dev_profile_lock_is_refused_by_its_header_not_by_its_git_line(tmp_path):
    text = _DEV_LOCK.read_text()
    mutated = re.sub(r"(?m)^decoy-engine @ git\+\S+$", "decoy-engine==0.18.0", text)
    assert mutated != text
    out = tmp_path / "sbom.cdx.json"
    pins = tmp_path / "requirements-dev.lock"
    pins.write_text(mutated)
    renamed = tmp_path / "runtime.txt"
    renamed.write_text(mutated)
    for p in (pins, renamed):
        r = _run(p, out)
        assert r.returncode != 0
        assert "dev profile" in r.stderr
        assert not out.exists()


def test_component_count_equals_pin_count(tmp_path):
    sbom = json.loads(_generate(tmp_path).read_text())
    pin_lines = [ln for ln in _FIXTURE_PINS.read_text().splitlines() if _PIN.match(ln)]
    assert len(sbom["components"]) == len(pin_lines)
    assert sorted((_norm(c["name"]), c["version"]) for c in sbom["components"]) == sorted(
        (_norm(m.group(1)), m.group(2)) for m in map(_PIN.match, pin_lines)
    )


def _load_checks():
    import importlib.util

    path = _SCRIPT.parent / "sbom_checks.py"
    spec = importlib.util.spec_from_file_location("sbom_checks", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_pin_violations_treats_crlf_like_the_script_path():
    checks = _load_checks()
    assert checks.pin_violations("six==1.17.0\r\n", require_hashes=False)
    assert checks.pin_violations("# x\r\nsix==1.17.0\n", require_hashes=False, allow_comments=True)
    assert checks.pin_violations("six==1.17.0\n", require_hashes=False) == []
