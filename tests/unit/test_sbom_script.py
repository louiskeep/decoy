"""R1-c: the CycloneDX SBOM generator for the CLI bundle (scripts/release/sbom.sh).

Runs the real script on a tiny fixture pin list (tests/fixtures/sbom_runtime) and
checks the output against the CycloneDX JSON schema, against the pin list
(completeness), for byte-identical reruns, and for leaks of paths or environment
values. Needs ``uv`` and network access to PyPI on first use (the pinned
``cyclonedx-py`` runs through ``uvx``).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

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
    assert ("numpy", "2.5.0") in _sbom_components(sbom)


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
    assert sbom["metadata"]["component"]["name"] == "sbom-fixture-cli"
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
    assert len(_pins(_RELEASE_PINS)) == 63
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
