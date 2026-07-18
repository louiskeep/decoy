# Fresh-install smoke runbook

This is the human-runnable version of `.github/workflows/release-smoke.yml`. Run it on a fresh Windows, macOS, or Linux box before tagging a release candidate. The OS matrix lives in OSS.7's publish pipeline (which extends this runbook to Windows + macOS CI); until then, this is what the human does by hand.

## What this proves

The OSS-CLI launch README §8 calls out R2 as the highest-impact unmitigated risk: "canonical smoke run has zero recorded executions on a fresh `pip install`." This runbook plus the CI workflow retires R2 by producing a recorded green run on a fresh venv at every release.

A green run end-to-end means:

1. The wheel builds via `hatchling`.
2. The wheel installs into a clean venv (no source tree visible to Python).
3. The console script `decoy` is wired (the `[project.scripts]` entry).
4. `decoy --version` runs and prints.
5. `decoy demo --json` runs end-to-end and exits 0.
6. `decoy templates list --json` returns the bundled set (5 entries, no `graph`).
7. `decoy run` against the bundled `minimal` template + a tmp CSV writes a masked output file.

Steps 5 + 6 + 7 exercise the engine import path; if `decoy-engine` is broken on the target Python version, steps 5-7 fail visibly and the release is held.

## Prerequisites

- Python 3.10, 3.11, or 3.12 installed and on `PATH`.
- `pip` and `venv` available.
- Network access to GitHub (for the pre-publish engine install via `git+https`).

## Steps (Linux + macOS)

```bash
# 1. Clone or fetch the repo at the tag you want to gate.
git clone https://github.com/louiskeep/decoy.git
cd decoy
git checkout v0.1.0   # or whichever tag

# 2. Build the wheel.
python -m pip install --upgrade pip build
python -m build --wheel

# 3. Create a clean install venv (NOT activated; we call into it
#    directly so the shell environment is irrelevant).
python -m venv .smoke

# 4. Install the engine from the sibling repo (pre-publish window).
#    Once OSS.7 lands the publish pipeline, swap to:
#       .smoke/bin/pip install decoy-engine
.smoke/bin/pip install --upgrade pip
.smoke/bin/pip install "git+https://github.com/louiskeep/decoy-engine@main"

# 5. Install the freshly-built decoy wheel.
.smoke/bin/pip install dist/*.whl

# 6. Smoke cells (each must exit 0).
.smoke/bin/decoy --version
.smoke/bin/decoy demo --json
.smoke/bin/decoy templates list --json

# 7. Canonical run cell. Use the bundled minimal template (NOT the
#    repo's examples/, which are repo-only and not in the wheel).
mkdir -p smoke_run
printf 'first_name,last_name,email,ssn,account_status\nAda,Lovelace,ada@example.com,000-00-0000,active\n' > smoke_run/input.csv
.smoke/bin/decoy templates show minimal > smoke_run/pipeline.yaml
cd smoke_run
../.smoke/bin/decoy run pipeline.yaml
test -s output.csv && echo "OK: output.csv written"
cd ..
```

Inspect `smoke_run/output.csv`: the email column should be a faker-generated value, not `ada@example.com`.

## Steps (Windows PowerShell)

```powershell
# 1. Clone or fetch the repo at the tag you want to gate.
git clone https://github.com/louiskeep/decoy.git
Set-Location decoy
git checkout v0.1.0

# 2. Build the wheel.
python -m pip install --upgrade pip build
python -m build --wheel

# 3. Create a clean install venv.
python -m venv .smoke

# 4. Install the engine from the sibling repo (pre-publish window).
.\.smoke\Scripts\pip.exe install --upgrade pip
.\.smoke\Scripts\pip.exe install "git+https://github.com/louiskeep/decoy-engine@main"

# 5. Install the freshly-built decoy wheel.
Get-ChildItem dist\*.whl | ForEach-Object {
    .\.smoke\Scripts\pip.exe install $_.FullName
}

# 6. Smoke cells.
.\.smoke\Scripts\decoy.exe --version
.\.smoke\Scripts\decoy.exe demo --json
.\.smoke\Scripts\decoy.exe templates list --json

# 7. Canonical run cell.
New-Item -ItemType Directory -Force smoke_run | Out-Null
"first_name,last_name,email,ssn,account_status`nAda,Lovelace,ada@example.com,000-00-0000,active" | Set-Content smoke_run\input.csv -Encoding utf8
.\.smoke\Scripts\decoy.exe templates show minimal | Set-Content smoke_run\pipeline.yaml -Encoding utf8
Set-Location smoke_run
..\.smoke\Scripts\decoy.exe run pipeline.yaml
if ((Get-Item output.csv).Length -gt 0) { Write-Output "OK: output.csv written" }
Set-Location ..
```

## Recording the run

After a successful run, append an entry to [`docs/release/smoke-log.md`](smoke-log.md) with the date, SHA you tested at, and (if running in CI) the workflow run URL. This is what retires R2: the line of paper that says "we have actually done this."

## Failure modes seen in practice

- **Engine resolution timeout**: the `git+https://github.com/louiskeep/decoy-engine@main` install step hits a transient GitHub error. Re-run; this is not a real failure.
- **Wheel build fails on Python 3.13+**: out of scope; OSS.1 pins 3.10-3.12.
- **`decoy templates show minimal` writes color codes to stdout**: default mode (no flags) is already raw YAML -- Rich highlighting is intentionally skipped so the output pipes cleanly to a file (see the command's docstring in `src/decoy/cli/templates.py`). There is no `--raw` flag; do not add `--raw` to the command (Typer will reject it with "No such option"; this was a real bug in this runbook + `release-smoke.yml` until the S3 fresh-install-smoke gate caught it by actually running the flow). If default-mode output still carries color codes, the bug is in `decoy templates show`; file an issue and do not work around with `sed`.
- **`decoy templates show minimal --json` doesn't decode as plain YAML**: `--json` wraps the body in a JSON envelope (`{"command": ..., "body": "<yaml>"}`); it is not a substitute for the default raw-YAML mode. Use no flag for the smoke's pipeline.yaml redirect.
- **`decoy run pipeline.yaml` exits 3 ("runtime error")**: read stderr. Common causes are a missing engine module, a wrong dependency version pinned upstream, or a real engine bug. Do not paper over with `--quiet`.
