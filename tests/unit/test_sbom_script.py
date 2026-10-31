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


def _pin(name: str) -> str:
    m = re.search(rf'^{name}="?([^"\n]+)"?$', _SCRIPT.read_text(), re.M)
    assert m, f"{name} pin not found in {_SCRIPT}"
    return m.group(1)


def _run(pins: Path, out: Path, env_extra: dict[str, str] | None = None, cwd: Path | None = None):
    _require_uv()
    return subprocess.run(
        ["bash", str(_SCRIPT), str(pins), str(out)],
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
            current = (m.group(1), m.group(2))
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
        comps.setdefault((c["name"], c["version"]), set()).update(hashes)
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
    # The pinned library's bundled strict JSON schema, in an isolated interpreter,
    # independent of the generator's own --validate step.
    code = (
        "import sys;"
        "from cyclonedx.schema import SchemaVersion;"
        "from cyclonedx.validation.json import JsonStrictValidator;"
        "t=open(sys.argv[1]).read();"
        "v=JsonStrictValidator(SchemaVersion.from_version(sys.argv[2]));"
        "e=v.validate_str(t);"
        "print('INVALID',e) if e else print('VALID');"
        "sys.exit(1 if e else 0)"
    )
    r = subprocess.run(
        [
            "uvx",
            "--from",
            f"cyclonedx-bom=={_pin('CYCLONEDX_BOM_VERSION')}",
            "--with",
            f"cyclonedx-python-lib=={_pin('CYCLONEDX_LIB_VERSION')}",
            "python",
            "-I",
            "-c",
            code,
            str(out),
            doc["specVersion"],
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0 and "VALID" in r.stdout, r.stdout + r.stderr


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


@pytest.mark.parametrize(
    "line",
    [
        "--index-url https://corp-index.internal.example/simple",
        "six @ file:///srv/vendored/six",
        "decoy-engine @ git+https://example.invalid/decoy-engine@abc",
        "-e ./local",
        "-r other.txt",
    ],
)
def test_non_pin_lines_fail_closed(tmp_path, line):
    pins = tmp_path / "requirements-runtime.txt"
    pins.write_text(f"six==1.17.0\n{line}\n")
    out = tmp_path / "sbom.cdx.json"
    r = _run(pins, out)
    assert r.returncode != 0
    assert "non-public source or unsupported requirement" in r.stderr
    assert not out.exists()


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
