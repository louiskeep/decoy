"""CI lock-install sentry (CI-L1a): hosted CLI jobs install from the lock, never re-resolve.

An unlocked install resolved pydantic-core 2.50.4 against a lock that pins 2.50.2 and CLI CI went
red. The scanner is tests/sentry/_ci_lock_scan.py, the policy ci/install-policy.toml. This file
holds the acceptance tests against the real files and the seeded cases that prove each rule can
go red.
"""

from __future__ import annotations

import copy
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Any

import pytest
import tomli
import yaml
from packaging.specifiers import SpecifierSet
from packaging.version import Version
from tests.sentry._ci_lock_scan import (
    LOCK_ENV_USES,
    ROOT,
    classify_install,
    engine_literals,
    load_policy,
    permission_findings,
    policy_findings,
    real_files,
    scan_repo,
    scan_workflow,
)
from tests.sentry.ci_scan._identity import fetch_raw, identity_findings, should_skip
from tests.sentry.ci_scan._shell_tokens import normalise

POLICY = load_policy()
SHA = "d4b2f3b6ecc6e67c4457f6d3e41ec42d3d0fcb86"
DEV = "-c requirements-dev.lock"
ENGINE = "git+https://github.com/louiskeep/decoy-engine@v0.18.0"
LE = {"uses": LOCK_ENV_USES}
WHEEL = f"uv pip install --python .smoke/bin/python {DEV} dist/*.whl"
SMOKE_CERT = ".venv-certified/bin/python scripts/cert_smoke.py"
needs_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


def _sh(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", *args], cwd=ROOT, env=env, capture_output=True, text=True, check=False
    )


def _scan(job: str, *steps: Any, name: str = "ci.yml", role: str = "workflow") -> list[str]:
    built = [{"run": s} if isinstance(s, str) else s for s in steps]
    wf = {"jobs": {job: {"steps": built}}}
    return scan_workflow(wf, policy=POLICY, name=name, role=role)


def _has(found: list[str], text: str) -> bool:
    return any(text in f for f in found)


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_cli_jobs_install_from_the_lock() -> None:
    files = real_files()
    assert {"ci.yml", "release-smoke.yml", "regen-diagrams.yml", "actions/lock-env"} <= set(files)
    assert not any("integrations" in n for n in files), "customer templates are not scanned"
    bad = scan_repo()
    assert not bad, "hosted jobs not installed from the lock:\n" + "\n".join(
        f"  {n}: {m}" for n, msgs in bad.items() for m in msgs
    )


def test_seeded_install_bypasses_are_found() -> None:
    cases = {
        "unlocked pytest": ([LE, "pip install -e .", "pytest tests"], "project install"),
        "fresh smoke without -c": ([LE, WHEEL.replace(DEV + " ", "")], "install without -c"),
        "unknown -r": ([LE, "pip install -r other.txt"], "unregistered requirements file"),
        "unknown -c": ([LE, "uv pip install -c other.lock dist/*.whl"], "unregistered constraint"),
        "no-deps elsewhere": ([LE, f"uv pip install --no-deps {DEV} dist/*.whl"], "--no-deps"),
        "engine literal": ([LE, f'run_x "{ENGINE}"'], "engine spec literal"),
        "bare tool": ([LE, f"uv pip install {DEV} build"], "not an exact == pin"),
        "tool without -c": ([LE, "uv pip install build==1.2.2"], "install without -c"),
        "uvx ruff": ([LE, "uvx ruff==0.15.14 check"], "ruff must come from"),
        "literal ruff": ([LE, 'pip install "ruff==0.15.14"'], "ruff must come from"),
        # Spellings the shared tokenizer normalises (catalog class 5).
        "env-var pip": ([LE, "$DECOY_VENV/bin/pip install pydantic-core"], "not an exact == pin"),
        "absolute pip -e": ([LE, "/usr/bin/pip install -e ."], "project install"),
        "smoke pip after wheel": ([LE, WHEEL, ".smoke/bin/pip install pydantic"], "not an exact"),
        "glued -r": ([LE, f"uv pip install {DEV} -rextra.txt"], "unregistered requirements"),
        "glued -i": ([LE, f"uv pip install {DEV} -ihttps://x/simple build==1.2.2"], "index"),
        "glued -e": ([LE, f"uv pip install {DEV} -e."], "project install"),
        "pip -rfile": ([LE, "pip install -rreqs.txt"], "unregistered requirements"),
        "uv run --with": ([LE, "uv run --with requests pytest"], "uv run --with"),
        "uv run unfrozen": ([LE, "uv run pytest"], "uv run without --frozen"),
        "bash -c body": ([LE, 'bash -c "pip install -e ."'], "project install"),
        "pip --opt=v": ([LE, "pip install --index-url=https://x/simple build==1.2.2"], "index"),
        "pip leading option": ([LE, "pip --quiet install requests"], "not an exact"),
        "pip3.11": ([LE, "pip3.11 install requests"], "not an exact"),
        "python -m pip": ([LE, "python -m pip install requests"], "not an exact"),
    }
    for label, (steps, expected) in cases.items():
        assert _has(_scan("fresh-install-smoke", *steps), expected), label
    assert _scan("fresh-install-smoke", LE, WHEEL, ".smoke/bin/decoy --version") == []
    assert _scan("pytest", LE, "uv run --frozen pytest") == []


def test_consumer_in_a_quoted_shell_body_is_ordered_and_visible() -> None:
    assert _has(_scan("pytest", 'bash -c "pytest tests"', LE), "before lock-env")
    assert _has(_scan("pytest", LE, 'bash -c "pytest || true"'), "hide a consumer failure")
    job = {"continue-on-error": True, "steps": [LE, {"run": "pytest tests"}]}
    assert _has(scan_workflow({"jobs": {"pytest": job}}, policy=POLICY, name="ci.yml"), "job-level")


def test_seeded_tool_option_and_index_bypasses_are_found() -> None:
    cases = {
        "uv global option before sync": ("uv --quiet sync", "re-resolves"),
        "uv pip sync": ("uv pip sync requirements.txt", "re-resolves"),
        "uv --directory add": ("uv --directory x add requests", "re-resolves"),
        "uv lock": ("uv lock", "re-resolves"),
        "uv remove": ("uv remove requests", "re-resolves"),
        "pipx run": ("pipx run ruff check", "fetches a tool"),
        "pipx install": ("pipx install requests", "fetches a tool"),
        "uv tool run": ("uv tool run black", "fetches a tool"),
        "uvx": ("uvx black", "fetches a tool"),
        "uv unknown option value before sync": ("uv --preview-features x sync", "re-resolves"),
        "uv tool install": ("uv tool install black", "fetches a tool"),
        "uv tool option value hides the verb": (
            "uv tool --python 3.12 run black",
            "fetches a tool",
        ),
        "uv tool cache-dir": ("uv tool --cache-dir c install black", "fetches a tool"),
        "uv tool empty option value": ("uv tool --python= run black", "fetches a tool"),
        "uv tool fetching verb after a harmless one": ("uv tool dir install", "fetches a tool"),
        "pip empty global option value": ("pip --python= install requests", "not an exact"),
        "uv pip empty global option value": ("uv pip --python= install requests", "not an exact"),
        "uv tool unknown options before the verb": ("uv tool --a x y run black", "fetches a tool"),
        "uv tool fetching verb later": ("uv tool --a b c install black", "fetches a tool"),
        "uv tool unknown verb": ("uv tool frobnicate black", "fetches a tool"),
        "uv tool unknown option": ("uv tool --brand-new v install black", "fetches a tool"),
        "uv tool run unfrozen with python": (
            "uv tool --python 3.12 run black",
            "uv run without --frozen",
        ),
        "uv unknown option before sync": ("uv --brand-new-option x sync", "re-resolves"),
        "uv unknown option before add": ("uv --brand-new-option x add requests", "re-resolves"),
        "uv two known names": ("uv --brand-new-option run sync", "re-resolves"),
        "uv value options": ("uv --cache-dir c --directory d --config-file f sync", "re-resolves"),
        "uv tool upgrade": ("uv tool upgrade black", "fetches a tool"),
        "uv tool run unfrozen": ("uv tool run black", "uv run without --frozen"),
        "pipx inject": ("pipx inject app requests", "fetches a tool"),
        "pipx upgrade": ("pipx upgrade app", "fetches a tool"),
        "pipx upgrade-all": ("pipx upgrade-all", "fetches a tool"),
        "pipx reinstall": ("pipx reinstall app", "fetches a tool"),
        "pipx runpip install": ("pipx runpip app install requests", "fetches a tool"),
        "uv --quiet pip sync": ("uv --quiet pip sync r.txt", "re-resolves"),
        "uv pip --system sync": ("uv pip --system sync r.txt", "re-resolves"),
        "uv pip -q sync": ("uv pip -q sync r.txt", "re-resolves"),
        "uv pip --python sync": ("uv pip --python p sync r.txt", "re-resolves"),
        "uv --directory run sync": ("uv --directory run sync --frozen", "re-resolves"),
        "pip global --python": ("pip --python .venv/bin/python install requests", "not an exact"),
        "uv pip --python before install": ("uv pip --python p install requests", "not an exact"),
        "pip --python=": ("pip --python=p install requests", "not an exact"),
        "find-links": (f"uv pip install {DEV} -f https://x dist/*.whl", "index"),
        "find-links long": (f"uv pip install {DEV} --find-links=https://x dist/*.whl", "index"),
        "find-links glued": (f"uv pip install {DEV} -fhttps://x dist/*.whl", "index"),
        "extra index": (f"uv pip install {DEV} --extra-index-url https://x dist/*.whl", "index"),
        "editable wheel": (f"uv pip install {DEV} -e dist/x.whl", "project install"),
        "editable wheel glued": (f"uv pip install {DEV} -edist/x.whl", "project install"),
        "editable engine": (
            f'uv pip install --no-deps -e "{ENGINE}" dist/x.whl',
            "project install",
        ),
        "wheel by url": (f"uv pip install {DEV} https://evil/x.whl", "project install"),
        "wheel outside dist": (f"uv pip install {DEV} /tmp/x.whl", "project install"),
        "wheel variable": (f'uv pip install {DEV} "$WHEEL"', "project install"),
        "no-binary": (f"uv pip install {DEV} --no-binary :all: dist/*.whl", "--no-binary"),
    }
    for label, (cmd, expected) in cases.items():
        assert _has(_scan("fresh-install-smoke", LE, cmd), expected), label
    for name in ("PIP_INDEX_URL", "PIP_EXTRA_INDEX_URL", "UV_INDEX_URL", "UV_EXTRA_INDEX_URL"):
        prefixed = f"{name}=https://x {WHEEL}"
        assert _has(_scan("fresh-install-smoke", LE, prefixed), "index environment"), name
        assert _has(_scan("fresh-install-smoke", LE, f"export {name}=https://x"), "index"), name
        assert _has(_scan("fresh-install-smoke", LE, {"env": {name: "x"}, "run": WHEEL}), "env")
        job = {"env": {name: "x"}, "steps": [LE]}
        assert _has(scan_workflow({"jobs": {"j": job}}, policy=POLICY, name="ci.yml"), "env"), name
        assert _has(scan_workflow({"env": {name: "x"}, "jobs": {}}, policy=POLICY), "env"), name
    assert (
        _scan(
            "fresh-install-smoke",
            LE,
            WHEEL,
            "uv --quiet pip install --python p " + DEV + " dist/*.whl",
        )
        == []
    )


def test_clean_commands_that_look_like_package_commands_stay_clean() -> None:
    clean = (
        "uv tool list",
        "uv tool dir",
        "uv tool --python 3.12 list",
        "uv tool --cache-dir c dir",
        "uv tool --python= list",
        "uv tool uninstall black",
        "uv tool update-shell",
        "uv run --frozen sync",
        "uv tool uninstall black",
        "pipx list",
        "pipx uninstall app",
        "pipx runpip app list",
        "rm -f build.log",
        "docker build -f Dockerfile .",
        "tail -f server.log",
        "grep -f patterns.txt data.txt",
        "ls -i",
        # `sync` is the value of --directory here; only `run` is the subcommand.
        "uv --directory sync run --frozen true",
    )
    for cmd in clean:
        assert _scan("fresh-install-smoke", LE, cmd) == [], cmd


def test_validators_are_anchored_with_fullmatch() -> None:
    newline = "build==1.2.2\n"
    assert _has(classify_install([newline], POLICY)[1], "not an exact")
    pinned = {"uses": f"astral-sh/setup-uv@{SHA}\n", "with": {"version": "0.11.19"}}
    assert _has(_scan("setup-uv", pinned, role="setup-uv"), "commit SHA")
    newer = {"uses": f"astral-sh/setup-uv@{SHA}", "with": {"version": "0.11.19\n"}}
    assert _has(_scan("setup-uv", newer, role="setup-uv"), "exact x.y.z")
    assert normalise(["pip", "install", "-rx\ny"]) == ["pip", "install", "-r", "x\ny"]
    for source in ("_ci_lock_scan.py", "ci_scan/_shell_tokens.py", "ci_scan/_identity.py"):
        text = _read(f"tests/sentry/{source}")
        assert not re.search(r"\.match\(|compile\(r?\"\^", text), f"{source} uses fullmatch"


def test_every_consumer_follows_its_jobs_route() -> None:
    for cmd in ("pytest tests", "ruff check src", "python scripts/build_docs.py"):
        assert _has(_scan("pytest", cmd, LE), "before lock-env"), cmd
    for cmd in (".smoke/bin/decoy --version", "../.smoke/bin/decoy run x.yaml", "decoy demo"):
        found = _scan("fresh-install-smoke", LE, cmd, WHEEL)
        assert _has(found, "before constrained-wheel"), cmd
    cert = _scan("certified-profile", LE, ".venv-certified/bin/python scripts/cert_smoke.py")
    assert _has(cert, "before certified-engine-wheel") and _has(cert, "before certified-closure")
    assert _has(_scan("mystery", LE, "pytest"), "no install route")
    for text in ("pytest || true", "set +e\npytest", "pytest\nexit 0"):
        assert _has(_scan("pytest", LE, text), "hide a consumer failure"), text
    for text in ("grep x requirements-dev.lock", "LOCK=requirements-dev.lock"):
        assert _has(_scan("ruff", LE, text), "inline lock parsing"), text


def test_setup_uv_is_pinned_and_used_once() -> None:
    steps = [s for d, _ in real_files().values() for j in d["jobs"].values() for s in j["steps"]]
    uv = [s for s in steps if str(s.get("uses", "")).startswith("astral-sh/setup-uv")]
    assert len(uv) == 1, (
        f"astral-sh/setup-uv appears {len(uv)} times; want only the setup-uv action"
    )
    assert uv[0]["uses"].endswith(f"@{SHA}") and uv[0]["with"]["version"] == "0.11.19"
    raw = {"uses": "astral-sh/setup-uv@v5", "with": {"version": "0.11.19"}}
    assert _has(_scan("pytest", raw), "raw setup-uv")
    for ref, version in (("v5", "0.11.19"), (SHA[:7], "0.11.19"), (SHA, "latest")):
        step = {"uses": f"astral-sh/setup-uv@{ref}", "with": {"version": version}}
        found = _scan("setup-uv", step, role="setup-uv")
        assert _has(found, "commit SHA") or _has(found, "exact x.y.z"), ref


def test_lock_profile_lives_in_lock_version_and_the_policy() -> None:
    for script in ("bootstrap.sh", "lock.sh"):
        text = _read(f"scripts/dev/{script}")
        assert "ci.yml" not in text and ".github/workflows" not in text, (
            f"{script} reads a workflow"
        )
    spec = _sh("scripts/dev/lock_version.sh", "--engine-spec").stdout.strip()
    literals = engine_literals()
    registered = {(s["workflow"], s["job"], s["step"]) for s in POLICY["engine_site"]}
    assert {(f, j, s) for f, j, s, _ in literals} == registered, "engine literals only at sites"
    assert {lit for *_, lit in literals} == {spec}, "every engine URL equals --engine-spec"
    pin = re.search(r'"decoy-engine==([^"]+)"', _read("pyproject.toml"))
    assert pin and spec.endswith(f"@v{pin.group(1)}"), "engine tag equals the pyproject pin"
    ruff = _sh("scripts/dev/lock_version.sh", "--ruff-pin").stdout.strip()
    assert re.search(rf"(?m)^ruff=={re.escape(ruff)} ", _read("requirements-dev.lock"))


def test_tool_installs_are_pinned_and_constrained() -> None:
    runs = [
        s.get("run", "")
        for d, _ in real_files().values()
        for j in d["jobs"].values()
        for s in j["steps"]
    ]
    builds = [r for r in runs if "build==1.2.2" in r]
    assert len(builds) == 3 and all(DEV in r for r in builds), builds
    regen = [r for r in runs if "pydeps" in r]
    assert (
        len(regen) == 1
        and DEV in regen[0]
        and "pydeps==3.0.9" in regen[0]
        and "pylint==4.1.3" in regen[0]
    )


def test_policy_ratchets_reasons_and_canary() -> None:
    assert sorted(s["kind"] for s in POLICY["engine_site"]) == ["certified", "drift-canary"]
    assert len(POLICY["write_scope"]) == 1, "write-scope allowlist is a ratchet at 1"
    assert policy_findings(POLICY) == []
    stripped = copy.deepcopy(POLICY)
    stripped["write_scope"][0]["reason"] = ""
    assert policy_findings(stripped)
    canary = {"name": "second canary", "if": "github.event_name == 'schedule'",
              "run": f'uv pip install --python p "{ENGINE}" dist/*.whl'}  # fmt: skip
    assert _has(
        _scan("fresh-install", LE, canary, name="release-smoke.yml"), "registered engine site"
    )


def test_certified_halves_are_each_required() -> None:
    site = next(s for s in POLICY["engine_site"] if s["kind"] == "certified")
    eng = {
        "name": site["step"],
        "run": f'uv pip install --python p --no-deps "{ENGINE}" dist/*.whl',
    }
    closure = "uv pip install --python p -r requirements-certified.txt"
    extra = {**eng, "run": eng["run"] + " pydantic-core==2.50.4"}
    for bad in (
        extra,
        {**eng, "run": eng["run"] + " other.whl"},
        {**eng, "run": eng["run"] + f' "{ENGINE}"'},
    ):
        assert _scan("certified-profile", LE, bad, closure, SMOKE_CERT), bad["run"]
    smoke = SMOKE_CERT
    assert _scan("certified-profile", LE, eng, closure, smoke) == []
    no_nodeps = {**eng, "run": eng["run"].replace("--no-deps ", "")}
    assert _scan("certified-profile", LE, no_nodeps, closure, smoke)
    assert _has(_scan("certified-profile", LE, eng, smoke), "before certified-closure")


def test_canary_is_exact_and_conditions_come_from_the_policy() -> None:
    site = next(s for s in POLICY["engine_site"] if s["kind"] == "drift-canary")
    cond = f"github.event_name == '{site['event']}'"
    step = {
        "name": site["step"],
        "if": cond,
        "run": f'uv pip install --python p "{ENGINE}" dist/*.whl',
    }
    ok = {"name": "wheel", "if": cond.replace("==", "!="), "run": WHEEL}
    scan = lambda *s, p=POLICY: scan_workflow(  # noqa: E731
        {"jobs": {"fresh-install": {"steps": [LE, *s]}}}, policy=p, name="release-smoke.yml"
    )
    assert scan(ok, step) == []
    assert scan(ok, {**step, "run": step["run"] + " pydantic-core==2.50.4"})
    assert scan(ok, {**step, "run": step["run"] + " other.whl"})
    for bad_if in ("github.event_name == 'push'", "always()", None):
        assert scan(ok, {**step, "if": bad_if}), bad_if
        assert scan({**ok, "if": bad_if}, step), bad_if
    # Each policy field, mutated, turns the real workflow red.
    real = real_files()["release-smoke.yml"][0]
    for field, value in (("event", "workflow_dispatch"), ("kind", "certified"), ("step", "x")):
        mutated = copy.deepcopy(POLICY)
        next(s for s in mutated["engine_site"] if s["kind"] == "drift-canary")[field] = value
        assert scan_workflow(real, policy=mutated, name="release-smoke.yml"), field
    for field in ("event", "reason"):
        mutated = copy.deepcopy(POLICY)
        next(s for s in mutated["engine_site"] if s["kind"] == "drift-canary")[field] = ""
        assert policy_findings(mutated), field
    cert = copy.deepcopy(POLICY)
    next(s for s in cert["engine_site"] if s["kind"] == "certified")["event"] = "schedule"
    assert policy_findings(cert), "only the canary names an event"


TOOLS = f"pip install --require-hashes --only-binary :all: -r {POLICY['locks']['ci_tools']}"
FETCH = 'python scripts/dev/fetch_ci_binary.py actionlint --dest "$RUNNER_TEMP/bin"'


def test_template_lint_installs_its_tools_from_the_hashed_lock() -> None:
    tools = _read("ci/ci-tools.in").split()
    lock = _read("ci/ci-tools.lock")
    assert tools and all(re.search(rf"(?m)^{re.escape(p)} \\", lock) for p in tools)
    assert "actionlint-py" not in lock, "actionlint-py is sdist-only; the binary replaces it"
    assert len(re.findall(r"--hash=sha256:", lock)) >= len(tools)
    script = _read("scripts/dev/lock.sh")
    body = re.search(r"compile_tools\(\) \{(.*?)\n\}", script, re.S)
    code = re.sub(r"#[^\n]*", "", body.group(1) if body else "")
    assert "--no-build" in code, "the tools lock is compiled wheel-only (comments do not count)"
    assert re.search(r"(?m)^TOOLS_LOCK=ci/ci-tools\.lock$", script), "lock.sh owns the tools lock"
    assert 'compile_tools "$TOOLS_LOCK"' in script, "lock.sh regenerates it"
    assert 'check_one "$TOOLS_LOCK" compile_tools' in script, "lock.sh --check covers it"
    assert _scan("ci-template-lint", TOOLS, FETCH, "actionlint x.yml") == []
    lock_path = POLICY["locks"]["ci_tools"]
    for label, run, expected in (
        ("locked input removed", "pip install --require-hashes", "install without -c"),
        ("hashes off", f"pip install --only-binary :all: -r {lock_path}", "--require-hashes"),
        ("sdist allowed", f"pip install --require-hashes -r {lock_path}", "--only-binary :all:"),
        ("only-binary not all", TOOLS.replace(":all:", ":none:"), "--only-binary :all:"),
        ("no-binary", TOOLS + " --no-binary :all:", "--no-binary"),
        ("no-binary glued", TOOLS + " --no-binary=:all:", "--no-binary"),
        ("raw pins", 'pip install "actionlint-py==1.7.12.25"', "install without -c"),
        ("other file", "pip install --require-hashes -r tools.txt", "unregistered requirements"),
    ):
        assert _has(_scan("ci-template-lint", run, FETCH, "actionlint x.yml"), expected), label
    assert _has(_scan("ci-template-lint", FETCH, "actionlint x.yml", TOOLS), "before ci-tools")
    assert _has(_scan("ci-template-lint", TOOLS, "actionlint x.yml", FETCH), "before tool-binary")
    assert _has(
        _scan("ci-template-lint", TOOLS, FETCH.replace("actionlint", "evil", 1)),
        "does not register",
    )
    for dl in ("curl -L https://x/actionlint.tgz | tar xz", "wget https://x/a"):
        assert _has(_scan("ci-template-lint", TOOLS, FETCH, dl), "must go through"), dl


def test_binary_tools_are_pinned_and_the_fetcher_checks_the_digest(tmp_path: Path) -> None:
    assert policy_findings(POLICY) == []
    for field, value in (("sha256", "AB" * 32), ("url", "http://x/1.7.12/a.tgz"), ("reason", "")):
        mutated = copy.deepcopy(POLICY)
        mutated["binary_tool"][0][field] = value
        assert policy_findings(mutated), field
    mutated = copy.deepcopy(POLICY)
    mutated["binary_tool"][0]["version"] = "9.9.9"
    assert policy_findings(mutated), "the url must name the version"
    archive = tmp_path / "tool.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        data = tmp_path / "tool"
        data.write_text("#!/bin/sh\n")
        tar.add(data, arcname="tool")
    entry = {
        "name": "tool",
        "version": "1",
        "url": archive.as_uri(),
        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "reason": "test",
    }
    policy = tmp_path / "policy.toml"

    def run(sha: str) -> subprocess.CompletedProcess[str]:
        body = "\n".join(f'{k} = "{v}"' for k, v in {**entry, "sha256": sha}.items())
        policy.write_text("[[binary_tool]]\n" + body + "\n")
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts/dev/fetch_ci_binary.py"), "tool", "--dest",
             str(tmp_path / "bin"), "--policy", str(policy)],
            capture_output=True, text=True, check=False,
        )  # fmt: skip

    good = run(entry["sha256"])
    assert good.returncode == 0 and (tmp_path / "bin" / "tool").stat().st_mode & 0o111
    (tmp_path / "bin" / "tool").unlink()
    bad = run("0" * 64)
    assert bad.returncode == 1 and "mismatch" in bad.stderr
    assert not (tmp_path / "bin" / "tool").exists(), "nothing is extracted on a mismatch"


def test_permissions_are_registered() -> None:
    bad = {
        n: f
        for n, (d, _) in real_files().items()
        if "/" not in n and (f := permission_findings(n, d, POLICY))
    }
    assert not bad, bad
    wide = {"permissions": {"contents": "read"}, "jobs": {"a": {"permissions": {"pages": "write"}}}}
    assert permission_findings("x.yml", wide, POLICY)
    assert permission_findings("x.yml", {"jobs": {}}, POLICY), "missing top-level block"
    used = {(n, j) for n, (d, _) in real_files().items() for j, job in {**d.get("jobs", {}), "": d}.items()
            if "write" in str((job or {}).get("permissions", ""))}  # fmt: skip
    assert used == {(w["workflow"], w["job"]) for w in POLICY["write_scope"]}


def _vendor_findings(ledger: dict[str, Any], root: Path = ROOT) -> list[str]:
    found = []
    for v in ledger["vendored"]:
        digest = hashlib.sha256((root / v["local_path"]).read_bytes()).hexdigest()
        if v["engine_path"] != v["local_path"] or digest != v["blob_sha256"]:
            found.append(f"{v['local_path']}: differs from engine path or sha256 in the ledger")
    for m in ledger["mirror"]:
        head = (root / m["local_path"]).read_text(encoding="utf-8")[:1500]
        if m["engine_path"] not in head or "ifferences" not in head:
            found.append(f"{m['local_path']}: header lacks the engine path or the differences")
    return found


def _ledger() -> dict[str, Any]:
    return tomli.loads(_read("ci/vendored.toml"))


def test_vendor_ledger_matches_the_copies(tmp_path: Path) -> None:
    ledger = _ledger()
    vendored = {v["local_path"] for v in ledger["vendored"]}
    shared = {
        f"tests/sentry/ci_scan/{p.name}" for p in (ROOT / "tests/sentry/ci_scan").glob("*.py")
    }
    assert shared <= vendored, (
        f"files in ci_scan missing from the ledger: {sorted(shared - vendored)}"
    )
    assert vendored - shared == {
        ".github/actions/setup-uv/action.yml",
        "tests/sentry/layout/_layout.py",
        "tests/sentry/layout/_ratchet_cases.py",
    }, "only setup-uv and the layout helpers besides"
    assert len(ledger["mirror"]) == 3
    assert _vendor_findings(ledger) == []
    wrong = copy.deepcopy(ledger)
    wrong["vendored"][0]["blob_sha256"] = "0" * 64
    moved = copy.deepcopy(ledger)
    moved["vendored"][0]["engine_path"] = "scripts/other.yml"
    assert _vendor_findings(wrong) and _vendor_findings(moved)
    for entry in ledger["vendored"]:
        local = tmp_path / entry["local_path"]
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes((ROOT / entry["local_path"]).read_bytes() + b"\n")
    n = len(ledger["vendored"])
    assert len(_vendor_findings({**ledger, "mirror": []}, tmp_path)) == n, "each copy is guarded"
    note = "After both repositories merge to main, the orchestrator re-points every `commit`"
    assert note in _read("ci/vendored.toml"), "the post-merge re-point instruction stays"


def test_vendored_files_are_byte_identical_to_the_engine_at_their_commit() -> None:
    for entry in _ledger()["vendored"]:
        assert re.fullmatch(r"[0-9a-f]{40}", entry["commit"]), f"{entry['engine_path']}: no commit"
        fetched = fetch_raw("louiskeep/decoy-engine", entry["commit"], entry["engine_path"])
        if should_skip(fetched, os.environ):
            pytest.skip("offline: the cross-repository check runs in CI and on networked builders")
        local = (ROOT / entry["local_path"]).read_bytes()
        assert identity_findings(local, entry["blob_sha256"], fetched) == [], entry["engine_path"]


def test_shared_shell_core_is_repo_neutral() -> None:
    text = _read("tests/sentry/ci_scan/_shell_tokens.py")
    for policy_word in ("install-policy", "requirements-", "decoy", "tomllib", "_ci_lock_scan"):
        assert policy_word not in text, f"the shared core must not know {policy_word}"
    scanner = _read("tests/sentry/_ci_lock_scan.py")
    assert "ci_scan._shell_tokens" in scanner
    for owned in ("def commands", "def normalise", "def parse_install_args", "_SHORT_VALUE"):
        assert owned not in scanner, f"{owned} belongs to the shared core only"


@needs_bash
def test_supported_minors_match_pyproject_and_the_matrices() -> None:
    supported = _sh("scripts/dev/lock_version.sh", "--supported-minors").stdout.split()
    spec = SpecifierSet(tomli.loads(_read("pyproject.toml"))["project"]["requires-python"])
    assert supported == ["3.10", "3.11", "3.12"] and all(
        Version(f"{m}.0") in spec for m in supported
    )
    assert Version("3.9.0") not in spec, "the minor below the supported set is excluded"
    ci = yaml.safe_load(_read(".github/workflows/ci.yml"))
    rs = yaml.safe_load(_read(".github/workflows/release-smoke.yml"))
    assert ci["jobs"]["pytest"]["strategy"]["matrix"]["python"] == supported
    assert rs["jobs"]["fresh-install"]["strategy"]["matrix"]["python"] == supported


@needs_bash
def test_bootstrap_rejects_an_unsupported_minor_and_verifies_once() -> None:
    bad = _sh("scripts/dev/bootstrap.sh", "--check", env={**os.environ, "DECOY_PYTHON": "3.9"})
    assert bad.returncode != 0 and "3.10 3.11 3.12" in bad.stderr, bad.stderr
    assert _read("scripts/dev/bootstrap.sh").count('"$PROFILE" --check') == 1
    action = _read(".github/actions/lock-env/action.yml").split("runs:")[1]
    assert "lock_version.sh" not in action, "lock-env leaves verification to bootstrap"
