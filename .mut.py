import hashlib, os, re, shutil, subprocess, sys, tempfile
ROOT = os.getcwd()
REPO = os.environ["MUT_REPO"]  # cli or eng
SC = "tests/sentry/ci_scan/_shell_tokens.py"
ID = "tests/sentry/ci_scan/_identity.py"
TI = "tests/sentry/ci_scan/test_identity.py"
SCAN = "tests/sentry/_ci_lock_scan.py"
TEST = "tests/sentry/test_ci_lock_installs.py"
LEDGER = "ci/vendored.toml" if REPO == "cli" else TEST
SEEDS = "not byte_identical"
CHECK = "byte_identical"
def rep(f, a, b): return (f, a, b)
M = {
 "C1 core: no basename": ([rep(SC, "    named = [\n        base(t)", "    named = [\n        t if True else base(t)")], SEEDS, SC),
 "C2 core: no short-value split": ([rep(SC, "elif _SHORT_VALUE.fullmatch(tok):", "elif False:")], SEEDS, SC),
 "C3 core: no --opt=v split": ([rep(SC, 'if tok.startswith("--") and "=" in tok:', "if False:")], SEEDS, SC),
 "C4 core: no bash -c body": ([rep(SC, "if (body := _shell_body(cmd)) is not None:", "if False:")], SEEDS, SC),
 "C5 core: no uv run checks": ([rep(SC, "    if not any(runs(pos) for pos in _uv_positions(cmd)):\n        return []", "    return []")], SEEDS, SC),
 "C6 core: pip global option values not skipped": ([rep(SC, "j += 2 if tokens[j] in with_value else 1", "j += 1")], SEEDS, SC),
 "C7 core: drops -e/--editable": ([rep(SC, 'elif arg in {"-e", "--editable"}:\n            parsed.editables.append(next(it, ""))\n        ', '')], SEEDS, SC),
 "C8 core: -f not an index override": ([rep(SC, '    "-f",\n    "--find-links",\n}\nINDEX_ENV', '}\nINDEX_ENV')], SEEDS, SC),
 "C9 core: no index env names": ([rep(SC, "return [n for n in names if n in INDEX_ENV]", "return []")], SEEDS, SC),
 "C10 core: no env-mapping index names": ([rep(SC, "return [k for k in env if k in INDEX_ENV] if isinstance(env, dict) else []", "return []")], SEEDS, SC),
 "C11 core: tool_fetch finds nothing": ([rep(SC, '    if "uvx" in cmd:\n        return "uvx"', '    return None\n    if "uvx" in cmd:\n        return "uvx"')], SEEDS, SC),
 "C12 core: uv global options not skipped": ([rep(SC, "    j = _skip_options(cmd, start, _UV_GLOBAL_VALUE)", "    j = start")], SEEDS, SC),
 "C13 core: --only-binary value dropped": ([rep(SC, 'parsed.values.setdefault(arg, []).append(next(it, ""))', 'next(it, None)')], SEEDS, SC),
 "C19 core: uv tool verb skips options with an empty set": ([rep(SC, "k = _skip_options(cmd, pos + 1, _UV_GLOBAL_VALUE)\n    return (cmd[k], k)", "k = _skip_options(cmd, pos + 1, set())\n    return (cmd[k], k)")], SEEDS, SC),
 "C20 core: uv tool fails open on an unknown verb": ([rep(SC, 'return None if not verb or verb in _UV_TOOL_NO_FETCH else (verb, k)', 'return (verb, k) if verb in {"install", "run", "upgrade"} else None')], SEEDS, SC),
 "C21 core: uv tool list treated as a fetch": ([rep(SC, '_UV_TOOL_NO_FETCH = {"list", "dir", "uninstall", "update-shell"}', '_UV_TOOL_NO_FETCH = {"dir", "uninstall", "update-shell"}')], SEEDS, SC),
 "C22 core: no fallback over unknown uv options": ([rep(SC, "    found = [k for k in range(start, len(cmd)) if cmd[k] in _UV_SUBCOMMANDS]\n    return found or ([j] if j < len(cmd) else [])", "    return [j] if j < len(cmd) else []")], SEEDS, SC),
 "C23 core: only the first known uv subcommand": ([rep(SC, "while run[-1] + 1 < len(cmd) and cmd[run[-1] + 1] in _UV_SUBCOMMANDS:", "while False:")], SEEDS, SC),
 "C24 core: pipx inject is not a fetch": ([rep(SC, '_PIPX_FETCH = {"install", "run", "inject", "upgrade", "upgrade-all", "reinstall", "reinstall-all"}', '_PIPX_FETCH = {"install", "run"}')], SEEDS, SC),
 "C25 core: pipx runpip install is not a fetch": ([rep(SC, 'if verb == "runpip" and "install" in cmd[k + 1 :]:', 'if False:')], SEEDS, SC),
 "C26 core: uv tool run is not a run": ([rep(SC, 'return fetch[0] == "run" or "run" in cmd[fetch[1] :]', "return False")], SEEDS, SC),
 "C27 core: is_package_command always true": ([rep(SC, '    return any(t in {"uv", "uvx", "pipx"} or is_pip(t) for t in cmd)', "    return True")], SEEDS, SC),
 "I1 identity: 5xx is not retried": ([rep(ID, "if err.code not in RETRY_STATUS and err.code < 500:", "if True:")], SEEDS, ID),
 "I2 identity: 404 is not a mismatch": ([rep(ID, "MISSING_STATUS = {404, 410}", "MISSING_STATUS = set()")], SEEDS, ID),
 "I3 identity: retries are unbounded in count": ([rep(ID, "TRIES = 3", "TRIES = 1")], SEEDS, ID),
 "I4 identity: skip even in CI": ([rep(ID, 'return fetched.status == "unreachable" and not env.get("CI")', 'return fetched.status == "unreachable"')], SEEDS, ID),
 "I5 identity: unreachable reported as differs": ([rep(ID, '''    elif fetched.status == "unreachable":
        found.append("the other repository's copy could not be fetched")
''', '')], SEEDS, ID),
 "I6 identity: ledger hash not compared": ([rep(ID, "if hashlib.sha256(local).hexdigest() != ledger_sha256:", "if False:")], SEEDS, ID),
 "X1 core edited + local hash recomputed": ([rep(SC, "def base(token", "def base (token")], CHECK, SC),
 "X2 ledger points at a commit without the core": ([], CHECK, None),
}
if REPO == "cli":
    M.update({
     "S1 scanner: .match for pins": ([rep(SCAN, "EXACT_PIN.fullmatch(arg)", "re.compile(r'[A-Za-z0-9_.\\-]+==[^<>=!~\\s]+').match(arg)")], SEEDS, None),
     "S2 scanner: version .match": ([rep(SCAN, 'VERSION.fullmatch(str((step.get("with") or {}).get("version", "")))', 'VERSION.match(str((step.get("with") or {}).get("version", "")))')], SEEDS, None),
     "S3 scanner: UV_REFRESH loses pip sync": ([rep(SCAN, ', "pip sync"}', "}")], SEEDS, None),
     "S4 ledger: a ci_scan row removed": ([], CHECK, None),
     "S5 ledger: re-point note removed": ([rep("ci/vendored.toml", "re-points every `commit` below", "x")], SEEDS, None),
    })
else:
    M.update({
     "E1 scanner: wheel-variable rule off": ([rep(SCAN, "    if names and all(n in wheels for n in names):\n        return None\n", "")], SEEDS, None),
     "E2 scanner: pip-audit --strict check off": ([rep(SCAN, 'if "--strict" not in cmd:', "if False:")], SEEDS, None),
     "E3 scanner: every job is the Mac gate": ([rep(SCAN, "exempt = is_mac_gate(name, job_name, job)", "exempt = True")], SEEDS, None),
     "E4 scanner: tool pin check off": ([rep(SCAN, 'return [] if EXACT_PIN.fullmatch(arg) else [f"tool is not an exact == pin ({arg})"]', "return []")], SEEDS, None),
     "E5 scanner: -r rule off": ([rep(SCAN, "for _ in parsed.requirements]", "for _ in []]")], SEEDS, None),
     "E6 scanner: -e rule off": ([rep(SCAN, "for _ in parsed.editables]", "for _ in []]")], SEEDS, None),
     "E7 scanner: uv add rule off": ([rep(SCAN, 'for sub in sorted(subs & {"add", "remove"}):', "for sub in []:")], SEEDS, None),
     "E8 scanner: uv lock rule off": ([rep(SCAN, 'if "lock" in subs and "--check" not in cmd:', "if False:")], SEEDS, None),
     "E9 scanner: index env rule off": ([rep(SCAN, 'findings += [f"index environment variable ({n})" for n in index_env_names(cmd)]', "")], SEEDS, None),
     "E10 scanner: uv pip sync not a sync": ([rep(SCAN, 'SYNC_SUBCOMMANDS = {"sync", "pip sync"}', 'SYNC_SUBCOMMANDS = {"sync"}')], SEEDS, None),
     "E11 scanner: index options on any command": ([rep(SCAN, "    if is_package_command(cmd):\n        findings += [f\"package index override", "    if True:\n        findings += [f\"package index override")], SEEDS, None),
     "E12 scanner: version .match": ([rep(SCAN, 'VERSION.fullmatch(str((step.get("with") or {}).get("version", "")))', 'VERSION.match(str((step.get("with") or {}).get("version", "")))')], SEEDS, None),
     "E13 scanner: sha .match": ([rep(SCAN, "SETUP_UV_SHA.fullmatch(uses)", "SETUP_UV_SHA.match(uses)")], SEEDS, None),
     "S4 ledger: a ci_scan row removed": ([], CHECK, None),
    })
def apply_ledger_edit(dst, name):
    p = os.path.join(dst, LEDGER)
    s = open(p).read()
    if name.startswith("X2"):
        if REPO == "cli":
            s = re.sub(r'(local_path = "tests/sentry/ci_scan/_shell_tokens.py"\nblob_sha256 = "[0-9a-f]+"\ncommit = ")[0-9a-f]{40}', r"\g<1>f2b7b3da4b9374b8745e089530b3e1c7815ce638", s)
        else:
            s = re.sub(r'("other_path": "tests/sentry/ci_scan/_shell_tokens.py",\n\s+"other_commit": ")[0-9a-f]{40}', r"\g<1>f2b7b3da4b9374b8745e089530b3e1c7815ce638", s)
    elif name.startswith("S4"):
        if REPO == "cli":
            s = re.sub(r'\[\[vendored\]\]\nengine_path = "tests/sentry/ci_scan/_identity.py".*?\n\n', "", s, flags=re.S)
        else:
            s = re.sub(r'    \{\n        "path": "tests/sentry/ci_scan/_identity.py",.*?\n    \},\n', "", s, flags=re.S)
    open(p, "w").write(s)
def rehash(dst, path):
    h = hashlib.sha256(open(os.path.join(dst, path), "rb").read()).hexdigest()
    p = os.path.join(dst, LEDGER)
    s = open(p).read()
    if REPO == "cli":
        s = re.sub(rf'(local_path = "{re.escape(path)}"\nblob_sha256 = ")[0-9a-f]+', r"\g<1>" + h, s)
    else:
        s = re.sub(rf'("path": "{re.escape(path)}",\n\s+"sha256": ")[0-9a-f]+', r"\g<1>" + h, s)
    open(p, "w").write(s)
only = sys.argv[1:]
res = []
for name, (edits, kexpr, rh) in M.items():
    if only and not any(name.startswith(o + " ") or name == o for o in only):
        continue
    tmp = tempfile.mkdtemp(); dst = os.path.join(tmp, "r")
    shutil.copytree(ROOT, dst, ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv*", ".smoke", ".mut.py"))
    ok = True
    for f, old, new in edits:
        p = os.path.join(dst, f); s = open(p).read()
        if old not in s:
            res.append((name, "PATCH-MISS", "")); ok = False; break
        open(p, "w").write(s.replace(old, new, 1))
    if not ok:
        continue
    if name.startswith(("X2", "S4")):
        apply_ledger_edit(dst, name)
    if rh:
        rehash(dst, rh)
    argv = [os.environ["PY"], "-m", "pytest", "tests/sentry/ci_scan", TEST, "-q", "-x", "-p", "no:cacheprovider", "-k", kexpr]
    r = subprocess.run(argv, cwd=dst, capture_output=True, text=True, env={**os.environ, "CI": "true"})
    last = [l for l in r.stdout.splitlines() if l.startswith(("FAILED", "ERROR"))][:1]
    res.append((name, "RED" if r.returncode == 1 else ("SURVIVED" if r.returncode == 0 else f"RC{r.returncode}"), last[0][:95] if last else ""))
    shutil.rmtree(tmp, ignore_errors=True)
for r in res:
    print(*r, sep=" | ")
print("NOT-RED:", [r[0] for r in res if r[1] != "RED"])
