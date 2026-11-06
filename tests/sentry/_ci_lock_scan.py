"""Scanner behind the CI lock-install sentry (CI-L1a): what a hosted CLI job may install, and how.

Mirror of the engine's tests/sentry/_ci_lock_scan.py (CI-E1); the tests are in
test_ci_lock_installs.py and the policy is ci/install-policy.toml.
Differences, deliberate until CI-X extracts one shared core:
- Same command tokenizer, install-argument parsing and setup-uv checks.
- CLI policy: two lock files, a per-job install route, engine spec only at registered sites.
- No pip-audit, pyarrow parity-smoke or Mac-gate rules; the CLI has no such job.
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

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[2]
POLICY_FILE = ROOT / "ci" / "install-policy.toml"
LOCK_ENV_USES = "./.github/actions/lock-env"
SETUP_UV_USES = "./.github/actions/setup-uv"
VERSION = re.compile(r"^\d+\.\d+\.\d+$")
SETUP_UV_SHA = re.compile(r"^astral-sh/setup-uv@[0-9a-f]{40}$")
ENGINE_URL = re.compile(r"git\+https://[^\s\"']*decoy-engine@[^\s\"']+")
INDEX_OPTIONS = {"--index-url", "--extra-index-url", "-i", "--index", "--default-index"}
SKIP_VALUE = {"--python", "-f", "--find-links", "-t", "--target", "--prefix", *INDEX_OPTIONS}
EXACT_PIN = re.compile(r"^[A-Za-z0-9_.\-]+(\[[A-Za-z0-9_,.\-]+\])?==[^<>=!~\s]+$")
_TOKEN = re.compile(r"\"[^\"]*\"|'[^']*'|\S+")
ENV_NAMES = ("UV_PROJECT_ENVIRONMENT", "DECOY_VENV", "DECOY_PYTHON")
_HIDES = re.compile(r"\|\|\s*(true|:|exit(\s+0)?)\b|\bset\s+(\+e\b|\+o\s+errexit)|\bexit\s+0\b")
_RUFF = re.compile(r"\bruff(\[[^\]]*\])?==|\buvx?\b[^\n]*\bruff\b")
DRIFT_IF = "github.event_name == 'schedule'"
NOT_DRIFT_IF = "github.event_name != 'schedule'"
CERT_KINDS = {"certified-engine-wheel": "certified", "drift-canary": "drift-canary"}


def load_policy(path: Path = POLICY_FILE) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _base(token: str) -> str:
    return token.rsplit("/", 1)[-1]


def _commands(text: str) -> list[list[str]]:
    """Commands of a step's shell: continuations joined, comments dropped, `--opt=v` split."""
    text = re.sub(r"\\\n\s*", " ", text.replace('\\"', '"'))
    commands: list[list[str]] = []
    for line in (ln.strip() for ln in text.splitlines()):
        if not line or line.startswith("#"):
            continue
        current: list[str] = []
        for raw in _TOKEN.findall(line):
            token = raw.strip("\"'") if raw[0] in "\"'" else raw
            if token in {"&&", "||", ";", "|"} or (token.endswith(";") and len(token) > 1):
                commands.append(current + ([token[:-1]] if token.endswith(";") else []))
                current = []
            elif token.startswith("--") and "=" in token:
                current += token.split("=", 1)
            else:
                current.append(token)
        commands.append(current)
    return [c for c in commands if c]


def _pip_install_args(cmd: list[str]) -> list[str] | None:
    """Arguments after `pip install` (pip, python -m pip, uv pip), or None if not one."""
    for i, tok in enumerate(cmd):
        if re.fullmatch(r"pip[0-9.]*", tok) and "install" in cmd[i + 1 :]:
            return cmd[cmd.index("install", i) + 1 :]
    return None


def _is_consumer(cmd: list[str], consumers: list[str]) -> bool:
    if _pip_install_args(cmd) is not None:
        return False
    return any(_base(t) in consumers or t.endswith(tuple(consumers)) for t in cmd)


def classify_install(
    args: list[str], policy: dict[str, Any], *, standalone: bool = False
) -> tuple[str | None, list[str]]:
    """The gate one pip install provides (constrained-wheel, drift-canary, certified-engine-wheel,
    certified-closure, or None for a constrained tool install) and its findings."""
    dev, cert = policy["locks"]["dev"], policy["locks"]["certified"]
    found: list[str] = []
    cons: list[str] = []
    reqs: list[str] = []
    wheels = engines = 0
    nodeps = bare = False
    it = iter(args)
    for arg in it:
        if arg in {"-c", "--constraint"}:
            cons.append(next(it, ""))
        elif arg in {"-r", "--requirement"}:
            reqs.append(next(it, ""))
        elif arg in INDEX_OPTIONS:
            found.append(f"package index override ({arg})")
            next(it, None)
        elif arg in SKIP_VALUE:
            next(it, None)
        elif arg in {"-e", "--editable"}:
            found.append(f"project install by pip ({arg})")
        elif arg == "--no-deps":
            nodeps = True
        elif arg.startswith("-"):
            continue
        elif ENGINE_URL.fullmatch(arg):
            engines += 1
        elif arg.endswith(".whl"):
            wheels += 1
        elif arg.startswith((".", "/", "$", "~")) or ("/" in arg and "==" not in arg):
            found.append(f"project install by pip ({arg})")
        elif not EXACT_PIN.match(arg):
            found.append(f"requirement is not an exact == pin ({arg})")
        else:
            bare = True
    found += [f"unregistered constraint file ({c})" for c in cons if c != dev]
    found += [f"unregistered requirements file ({r})" for r in reqs if r != cert]
    gate: str | None = None
    if reqs == [cert] and not (cons or wheels or engines or bare):
        gate = "certified-closure"
    elif engines and wheels and not (cons or reqs):
        gate = "certified-engine-wheel" if nodeps else "drift-canary"
    elif engines:
        found.append("engine spec outside the registered certified and drift-canary installs")
    elif cons == [dev] and not reqs:
        gate = "constrained-wheel" if wheels else None
    elif not (standalone and not (cons or reqs or wheels)):
        found.append(f"install without -c {dev}")
    if nodeps and gate != "certified-engine-wheel":
        found.append("--no-deps outside the certified engine-plus-wheel install")
    return gate, found


def _is_site(policy: dict[str, Any], name: str, job: str, step: dict[str, Any], kind: str) -> bool:
    key = (name, job, str(step.get("name", "")), kind)
    return any(
        (s["workflow"], s["job"], s["step"], s["kind"]) == key for s in policy["engine_site"]
    )


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
    for cmd in _commands(text):
        args = _pip_install_args(cmd)
        if args is None:
            if any(lk in tok for tok in cmd for lk in policy["locks"].values()):
                out.append("inline lock parsing; use scripts/dev/lock_version.sh")
            if "uv" in cmd and cmd[cmd.index("uv") + 1 : cmd.index("uv") + 2] in (
                [["add"], ["remove"], ["lock"], ["sync"]]
            ):
                out.append("uv add, remove, lock or sync re-resolves outside the lock")
            if ctx["role"] == "workflow" and any(_base(t) == "bootstrap.sh" for t in cmd):
                out.append(f"installs outside {LOCK_ENV_USES}")
            if "uvx" in cmd or ("uv" in cmd and "tool" in cmd):
                out.append("uvx and uv tool fetch tools from the index; use the lock")
            continue
        gate, found = classify_install(args, policy, standalone=route == ["standalone"])
        out += found
        if gate:
            gates.append(gate)
        if gate in CERT_KINDS and not _is_site(policy, name, job, step, CERT_KINDS[gate]):
            out.append(f"{gate} install is not a registered engine site")
        if gate == "drift-canary" and step.get("if") != DRIFT_IF:
            out.append(f"the drift canary must run only when {DRIFT_IF}")
        if (
            gate == "constrained-wheel"
            and "drift-canary" in route
            and step.get("if") != NOT_DRIFT_IF
        ):
            out.append(f"the constrained install must skip the drift-canary event ({NOT_DRIFT_IF})")
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
    for job_name, job in (wf.get("jobs") or {}).items():
        steps = job.get("steps") or []
        entry = next(
            (r for r in policy["route"] if (r["workflow"], r["job"]) == (name, job_name)), None
        )
        route = entry["gates"] if entry else []
        ctx = {"policy": policy, "role": role, "route": route}
        gate_at: dict[str, int] = {}
        installs = False
        uses = [str(s.get("uses", "")) for s in steps]
        if role == "workflow" and any(n in (job.get("env") or {}) for n in ENV_NAMES):
            findings.append(f"{job_name}: copies the venv env block; use {LOCK_ENV_USES}")
        for index, step in enumerate(steps):
            if uses[index] == LOCK_ENV_USES:
                gate_at.setdefault("lock-env", index)
            found, gates = _step_findings(name, job_name, step, ctx)
            findings += found
            for gate in gates:
                gate_at.setdefault(gate, index)
            cmds = _commands(str(step.get("run", "")))
            installs = installs or any(_pip_install_args(c) is not None for c in cmds)
            if role == "workflow" and not {LOCK_ENV_USES, SETUP_UV_USES} & set(uses):
                if any(t in {"uv", "uvx"} for c in cmds for t in c):
                    findings.append(f"{job_name}: runs uv without the setup-uv or lock-env action")
            if not any(_is_consumer(c, policy["consumers"]) for c in cmds):
                continue
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
        if installs and not route:
            findings.append(f"{job_name}: installs packages but has no route in the policy")
        order = [gate_at[g] for g in route if g in gate_at]
        if order != sorted(order):
            findings.append(f"{job_name}: install gates run out of the registered order")
        for step in steps:
            ref = str(step.get("uses", ""))
            if not ref.startswith("astral-sh/setup-uv"):
                continue
            if not VERSION.match(str((step.get("with") or {}).get("version", ""))):
                findings.append(f"{job_name}: setup-uv version is not an exact x.y.z")
            if not SETUP_UV_SHA.match(ref):
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
    """Every engine site and write scope names a reason; that is what makes it a decision."""
    return [
        f"{t} {e.get('workflow')}/{e.get('job')} has no reason"
        for t in ("engine_site", "write_scope")
        for e in policy.get(t, [])
        if not str(e.get("reason", "")).strip()
    ]


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
