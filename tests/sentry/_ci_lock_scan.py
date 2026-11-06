"""Scanner behind the CI lock-install sentry (CI-L1a): what a hosted CLI job may install, and how.

Mirror of the engine's tests/sentry/_ci_lock_scan.py (CI-E1); the tests are in
test_ci_lock_installs.py and the policy is ci/install-policy.toml.
The shell parsing (command splitting, basename and option normalisation, pip install arguments,
uv run checks) is not here: it lives in ci_scan/_shell_tokens.py, one byte-identical file the engine
adopts too, so the two scanners parse alike. Differences from the engine scanner, each
deliberate, and every rule the CLI drops is listed with its reason:
- CLI policy in ci/install-policy.toml: three lock files, a per-job install route, engine spec and
  the drift-canary event only at registered sites, release binaries only through
  scripts/dev/fetch_ci_binary.py with a checked sha256.
- Dropped, stricter in the CLI: the wheel-variable rule (`pip install "$WHEEL"` is a finding here),
  pinned-tool allowance (uvx, `uv tool` and pipx fetches are all findings), `uv lock --check` and
  `uv sync --frozen` (every uv sync or lock is a finding; bootstrap.sh owns the install).
- Dropped, no such job in the CLI: pip-audit matrix rules, pyarrow parity-smoke, the Mac gate
  exemption, and the CodSpeed `with.run` step text.
- Replaced: the inline-lock-parsing target (`requirements-dev.lock` and the other registered lock
  files instead of `uv.lock`) and the write-scope allowlist (policy `write_scope`).
- Discovery is bounded to .github/workflows and .github/actions. Customer templates under
  integrations/ are shipped product and are never scanned.
Order is checked by step index, not data flow.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml
from tests.sentry.ci_scan._shell_tokens import (
    EXACT_PIN,
    base,
    commands,
    env_mapping_index_names,
    index_env_names,
    parse_install_args,
    pip_install_args,
    tool_fetch,
    uv_run_findings,
    uv_subcommands,
)

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[2]
POLICY_FILE = ROOT / "ci" / "install-policy.toml"
LOCK_ENV_USES = "./.github/actions/lock-env"
SETUP_UV_USES = "./.github/actions/setup-uv"
VERSION = re.compile(r"\d+\.\d+\.\d+")
SETUP_UV_SHA = re.compile(r"astral-sh/setup-uv@[0-9a-f]{40}")
LOCAL_WHEEL = re.compile(r"(\./)?dist/[^/\s]+\.whl")
FETCH_SCRIPT = "fetch_ci_binary.py"
# uv subcommands that resolve or edit outside the lock.
UV_REFRESH = {"sync", "add", "remove", "lock", "pip sync"}
ENGINE_URL = re.compile(r"git\+https://[^\s\"']*decoy-engine@[^\s\"']+")
ENV_NAMES = ("UV_PROJECT_ENVIRONMENT", "DECOY_VENV", "DECOY_PYTHON")
_HIDES = re.compile(r"\|\|\s*(true|:|exit(\s+0)?)\b|\bset\s+(\+e\b|\+o\s+errexit)|\bexit\s+0\b")
_RUFF = re.compile(r"\bruff(\[[^\]]*\])?==|\buvx?\b[^\n]*\bruff\b")
# Lock key in the policy -> the install gate `-r <that file>` provides.
REQ_GATES = {"certified": "certified-closure", "ci_tools": "ci-tools"}
CERT_KINDS = {"certified-engine-wheel": "certified", "drift-canary": "drift-canary"}


def load_policy(path: Path = POLICY_FILE) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _is_consumer(cmd: list[str], consumers: list[str]) -> bool:
    if pip_install_args(cmd) is not None or FETCH_SCRIPT in map(base, cmd):
        return False
    return any(base(t) in consumers or t.endswith(tuple(consumers)) for t in cmd)


def classify_install(args: list[str], policy: dict[str, Any]) -> tuple[str | None, list[str]]:
    """The gate one pip install provides (constrained-wheel, drift-canary, certified-engine-wheel,
    certified-closure, ci-tools, or None for a constrained tool install) and its findings."""
    locks = policy["locks"]
    dev = locks["dev"]
    parsed = parse_install_args(args)
    cons, reqs, flags = parsed.constraints, parsed.requirements, parsed.flags
    found = [f"package index override ({o})" for o in parsed.index_overrides]
    found += [f"project install by pip (-e {e})" for e in parsed.editables]
    wheels = engines = 0
    bare = False
    for arg in parsed.positionals:
        if ENGINE_URL.fullmatch(arg):
            engines += 1
        elif LOCAL_WHEEL.fullmatch(arg):
            wheels += 1
        elif arg.startswith((".", "/", "$", "~")) or ("/" in arg and "==" not in arg):
            found.append(f"project install by pip ({arg})")
        elif not EXACT_PIN.fullmatch(arg):
            found.append(f"requirement is not an exact == pin ({arg})")
        else:
            bare = True
    nodeps = "--no-deps" in flags
    if "--no-binary" in parsed.values or "--no-binary" in flags:
        found.append("source builds (--no-binary) resolve unpinned build dependencies")
    found += [f"unregistered constraint file ({c})" for c in cons if c != dev]
    closures = {locks[k]: g for k, g in REQ_GATES.items()}
    found += [f"unregistered requirements file ({r})" for r in reqs if r not in closures]
    gate: str | None = None
    exact_pair = engines == 1 and wheels == 1 and not bare and not (cons or reqs)
    if len(reqs) == 1 and reqs[0] in closures and not (cons or wheels or engines or bare):
        gate = closures[reqs[0]]
        if gate == "ci-tools" and "--require-hashes" not in flags:
            found.append("the ci-tools lock must be installed with --require-hashes")
        if gate == "ci-tools" and parsed.values.get("--only-binary") != [":all:"]:
            found.append("the ci-tools lock must be installed with --only-binary :all:")
    elif exact_pair:
        gate = "certified-engine-wheel" if nodeps else "drift-canary"
    elif engines:
        found.append(
            "engine spec outside the exact engine-plus-wheel certified and canary installs"
        )
    elif cons == [dev] and not reqs:
        gate = "constrained-wheel" if wheels else None
    else:
        found.append(f"install without -c {dev}")
    if nodeps and gate != "certified-engine-wheel":
        found.append("--no-deps outside the certified engine-plus-wheel install")
    return gate, found


def _is_site(policy: dict[str, Any], name: str, job: str, step: dict[str, Any], kind: str) -> bool:
    key = (name, job, str(step.get("name", "")), kind)
    return any(
        (s["workflow"], s["job"], s["step"], s["kind"]) == key for s in policy["engine_site"]
    )


def canary_event(policy: dict[str, Any], name: str, job: str) -> str | None:
    """The event the job's registered drift canary runs on; the policy is the only source."""
    return next(
        (
            s.get("event")
            for s in policy["engine_site"]
            if s["kind"] == "drift-canary" and (s["workflow"], s["job"]) == (name, job)
        ),
        None,
    )


def _event_if(event: str | None, op: str) -> str:
    return f"github.event_name {op} '{event}'"


def _step_findings(
    name: str, job: str, step: dict[str, Any], ctx: dict[str, Any]
) -> tuple[list[str], list[str]]:
    """Findings that need only one step, and the install gates the step provides."""
    policy, route = ctx["policy"], ctx["route"]
    text, out, gates = str(step.get("run", "")), [], []
    if ctx["role"] == "workflow" and (
        re.search(rf"({'|'.join(ENV_NAMES)})=.*GITHUB_ENV", text)
        or any(n in (step.get("env") or {}) for n in ENV_NAMES)
    ):
        out.append(f"copies the venv env block; use {LOCK_ENV_USES}")
    literal = ENGINE_URL.search(text)
    if literal and not any(_is_site(policy, name, job, step, k) for k in CERT_KINDS.values()):
        out.append("engine spec literal outside the registered install sites")
    if _RUFF.search(text):
        out.append(f"ruff must come from {LOCK_ENV_USES}, not a literal pin or uvx")
    out += [
        f"index environment variable ({n}) in env" for n in env_mapping_index_names(step.get("env"))
    ]
    for cmd in commands(text):
        out += uv_run_findings(cmd, frozen_env=ctx["frozen"])
        out += [f"index environment variable ({n})" for n in index_env_names(cmd)]
        if refresh := [sub for sub in uv_subcommands(cmd) if sub in UV_REFRESH]:
            out.append(f"uv {refresh[0]} re-resolves outside the lock")
        if fetch := tool_fetch(cmd):
            out.append(f"{fetch[0]} fetches a tool from the index; use the lock")
        if any(base(t) in {"curl", "wget"} for t in cmd):
            out.append(f"downloads must go through {FETCH_SCRIPT} (sha256-checked)")
        if FETCH_SCRIPT in map(base, cmd):
            gates.append("tool-binary")
            tool = cmd[list(map(base, cmd)).index(FETCH_SCRIPT) + 1 :][:1]
            if not tool or tool[0] not in {t["name"] for t in policy.get("binary_tool", [])}:
                out.append(f"{FETCH_SCRIPT} names a tool the policy does not register")
        args = pip_install_args(cmd)
        if args is None:
            if any(lk in tok for tok in cmd for lk in policy["locks"].values()):
                out.append("inline lock parsing; use scripts/dev/lock_version.sh")
            if ctx["role"] == "workflow" and any(base(t) == "bootstrap.sh" for t in cmd):
                out.append(f"installs outside {LOCK_ENV_USES}")
            continue
        gate, found = classify_install(args, policy)
        out += found
        if gate:
            gates.append(gate)
        if gate in CERT_KINDS and not _is_site(policy, name, job, step, CERT_KINDS[gate]):
            out.append(f"{gate} install is not a registered engine site")
        event = canary_event(policy, name, job)
        want = {"drift-canary": "==", "constrained-wheel": "!="}.get(gate or "")
        if want and (gate == "drift-canary" or "drift-canary" in route):
            if event is None or step.get("if") != _event_if(event, want):
                out.append(f"the {gate} install must run under `{_event_if(event, want)}`")
    return [f"{job}: {m}" for m in out], gates


def scan_workflow(
    wf: dict[str, Any],
    *,
    policy: dict[str, Any] | None = None,
    role: str = "workflow",
    name: str = "",
) -> list[str]:
    """Every lock-install violation in one parsed workflow or action, as `job: message` strings.

    `role` is "lock-env" or "setup-uv" for that action itself; `name` is the workflow file name
    (or `actions/<dir>`), which keys the routes and engine sites in the policy."""
    policy = load_policy() if policy is None else policy
    findings: list[str] = []
    if role == "workflow" and any(n in (wf.get("env") or {}) for n in ENV_NAMES):
        findings.append("workflow: copies the venv env block; use " + LOCK_ENV_USES)
    findings += [
        f"workflow: index environment variable ({n}) in env"
        for n in env_mapping_index_names(wf.get("env"))
    ]
    for job_name, job in (wf.get("jobs") or {}).items():
        steps = job.get("steps") or []
        entry = next(
            (r for r in policy["route"] if (r["workflow"], r["job"]) == (name, job_name)), None
        )
        route = entry["gates"] if entry else []
        frozen = any(
            str((e or {}).get("UV_FROZEN")) == "1" for e in (wf.get("env"), job.get("env"))
        )
        ctx = {"policy": policy, "role": role, "route": route, "frozen": frozen}
        gate_at: dict[str, int] = {}
        installs = consumer_seen = False
        uses = [str(s.get("uses", "")) for s in steps]
        findings += [
            f"{job_name}: index environment variable ({n}) in env"
            for n in env_mapping_index_names(job.get("env"))
        ]
        if role == "workflow" and any(n in (job.get("env") or {}) for n in ENV_NAMES):
            findings.append(f"{job_name}: copies the venv env block; use {LOCK_ENV_USES}")
        for index, step in enumerate(steps):
            if uses[index] == LOCK_ENV_USES:
                gate_at.setdefault("lock-env", index)
            found, gates = _step_findings(name, job_name, step, ctx)
            findings += found
            for gate in gates:
                gate_at.setdefault(gate, index)
            cmds = commands(str(step.get("run", "")))
            installs = installs or bool(gates) or any(pip_install_args(c) is not None for c in cmds)
            if role == "workflow" and not {LOCK_ENV_USES, SETUP_UV_USES} & set(uses):
                if any(t in {"uv", "uvx"} for c in cmds for t in c):
                    findings.append(f"{job_name}: runs uv without the setup-uv or lock-env action")
            if not any(_is_consumer(c, policy["consumers"]) for c in cmds):
                continue
            consumer_seen = True
            if not route:
                findings.append(
                    f"{job_name}: consumer step {index} but no install route in the policy"
                )
            findings += [
                f"{job_name}: step {index} runs a consumer before {g}"
                for g in route
                if g not in gate_at or gate_at[g] >= index
            ]
            if step.get("continue-on-error") not in (None, False, "false") or _HIDES.search(
                str(step.get("run", ""))
            ):
                findings.append(f"{job_name}: step {index} can hide a consumer failure")
        if consumer_seen and job.get("continue-on-error") not in (None, False, "false"):
            findings.append(f"{job_name}: job-level continue-on-error can hide a consumer failure")
        if installs and not route:
            findings.append(f"{job_name}: installs packages but has no route in the policy")
        order = [gate_at[g] for g in route if g in gate_at]
        if order != sorted(order):
            findings.append(f"{job_name}: install gates run out of the registered order")
        for step in steps:
            ref = str(step.get("uses", ""))
            if not ref.startswith("astral-sh/setup-uv"):
                continue
            if not VERSION.fullmatch(str((step.get("with") or {}).get("version", ""))):
                findings.append(f"{job_name}: setup-uv version is not an exact x.y.z")
            if not SETUP_UV_SHA.fullmatch(ref):
                findings.append(f"{job_name}: setup-uv is not pinned to a commit SHA")
            if role != "setup-uv":
                findings.append(f"{job_name}: raw setup-uv; use {SETUP_UV_USES}")
    return sorted(set(findings))


def real_files(root: Path = ROOT) -> dict[str, tuple[dict[str, Any], str]]:
    """Every workflow and composite action under .github, found by walking: name -> (doc, role)."""
    files: dict[str, tuple[dict[str, Any], str]] = {}
    for p in sorted((root / ".github" / "workflows").glob("*.y*ml")):
        files[p.name] = (yaml.safe_load(p.read_text(encoding="utf-8")), "workflow")
    for p in sorted((root / ".github" / "actions").glob("**/action.y*ml")):
        steps = (yaml.safe_load(p.read_text(encoding="utf-8")).get("runs") or {}).get("steps") or []
        role = p.parent.name if p.parent.name in {"lock-env", "setup-uv"} else "workflow"
        files[f"actions/{p.parent.name}"] = ({"jobs": {p.parent.name: {"steps": steps}}}, role)
    return files


def scan_repo(root: Path = ROOT, policy: dict[str, Any] | None = None) -> dict[str, list[str]]:
    policy = load_policy(root / "ci" / "install-policy.toml") if policy is None else policy
    scanned = {
        n: scan_workflow(d, policy=policy, role=r, name=n) for n, (d, r) in real_files(root).items()
    }
    return {n: found for n, found in scanned.items() if found}


def engine_literals(root: Path = ROOT) -> list[tuple[str, str, str, str]]:
    """(file, job, step name, spec) for every engine spec literal in any scanned step."""
    return [
        (n, j, str(s.get("name", "")), m)
        for n, (d, _) in real_files(root).items()
        for j, job in (d.get("jobs") or {}).items()
        for s in job.get("steps") or []
        for m in ENGINE_URL.findall(str(s.get("run", "")))
    ]


def policy_findings(policy: dict[str, Any]) -> list[str]:
    """Every engine site, binary tool and write scope names a reason; a drift canary also names its event and
    no other site does. That is what makes each one a decision."""
    found = [
        f"{t} {e.get('workflow') or e.get('name')}/{e.get('job', '')} has no reason"
        for t in ("engine_site", "write_scope", "binary_tool")
        for e in policy.get(t, [])
        if not str(e.get("reason", "")).strip()
    ]
    for site in policy.get("engine_site", []):
        where = f"engine_site {site.get('workflow')}/{site.get('job')}"
        if site.get("kind") not in set(CERT_KINDS.values()):
            found.append(f"{where} has unknown kind {site.get('kind')!r}")
        if (site.get("kind") == "drift-canary") != bool(str(site.get("event", "")).strip()):
            found.append(f"{where}: only a drift-canary names an event, and it must")
    for tool in policy.get("binary_tool", []):
        where = f"binary_tool {tool.get('name')}"
        if not re.fullmatch(r"[0-9a-f]{64}", str(tool.get("sha256", ""))):
            found.append(f"{where}: sha256 is not 64 lowercase hex digits")
        if not (
            str(tool.get("url", "")).startswith("https://")
            and str(tool.get("version", "x")) in str(tool.get("url", ""))
        ):
            found.append(f"{where}: url is not https or does not name the version")
    return found


def permission_findings(name: str, wf: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    """A workflow declares top-level permissions, and only registered places hold write scopes."""
    allow = {(w["workflow"], w["job"]): set(w["scopes"]) for w in policy["write_scope"]}
    places = {"": wf.get("permissions")} | {
        j: job["permissions"] for j, job in (wf.get("jobs") or {}).items() if "permissions" in job
    }
    findings = []
    if not isinstance(places[""], dict):
        findings.append(f"{name}: no top-level permissions mapping (got {places['']!r})")
    for place, perms in places.items():
        if not isinstance(perms, dict):
            findings += [f"{name} {place}: permissions is not a mapping"] if place else []
            continue
        extra = {k for k, v in perms.items() if str(v) not in {"read", "none"}}
        if extra - allow.get((name, place), set()):
            findings.append(
                f"{name} {place or 'workflow'}: write scopes {sorted(extra)} unregistered"
            )
    return findings
