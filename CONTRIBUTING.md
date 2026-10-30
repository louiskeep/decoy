# Contributing to decoy

Thanks for considering a contribution. `decoy` is the CLI front end for [`decoy-engine`](https://github.com/louiskeep/decoy-engine); most data-plane changes belong in the engine repo rather than here.

## Reporting bugs and requesting features

[GitHub Issues](https://github.com/louiskeep/decoy/issues) is the right channel for both. A good bug report includes:

- CLI version (`decoy --version`)
- Engine version (`python -c "import decoy_engine; print(decoy_engine.__version__)"`)
- The exact command you ran
- A minimal `pipeline.yaml` that reproduces the issue (omit any real data)
- The full traceback or `--json` error envelope

For security issues, do not file a public issue: see [`SECURITY.md`](SECURITY.md).

## Local development

```
git clone https://github.com/louiskeep/decoy
cd decoy
python -m venv .venv
source .venv/bin/activate    # PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Tests:

```
pytest tests/unit/
pytest tests/e2e/
```

A green local run on Python 3.10, 3.11, and 3.12 is the bar before requesting review.

### Pinned environment and local gates (workers)

- `scripts/dev/bootstrap.sh` makes `.venv` match `requirements-dev.lock` exactly (`uv pip sync`, hashes verified), then installs the CLI editable with `--no-deps`. It fails if the lock is missing, stale against `pyproject.toml`/`ci.yml`, or any installed version differs from it, and prints the fix. `--check` verifies without installing.
- `requirements-dev.lock` is the dev/test closure `ci.yml`'s pytest and ruff jobs install (`.[dev]`, the engine's pinned git tag locked to its commit, the ruff pin) for CPython 3.10 on x86_64 Linux. Only `scripts/dev/lock.sh` writes it; `lock.sh --check` is the staleness test. It is unrelated to `requirements-certified.txt`, the frozen runtime-only closure of the certified DP stack: different purpose and package set, and the two may pin the same package differently. Never derive one from the other.
- `scripts/dev/gates.sh [paths...]` runs the env check, ruff check, `tests/sentry`, then the given tests (default: tests touching files changed against `origin/main`), stopping at the first failure unless `--keep-going`. `ci.yml` has no mypy or format gate, so those steps report SKIP.
- It ends with an EVIDENCE block (commands, tool versions, per-step counts, failing test ids). Paste that block into evidence files instead of summarizing.
- `--baseline` reruns the same steps on `origin/main` in a temporary detached worktree with the same venv and labels each failing id BOTH, BRANCH-ONLY or BASELINE-ONLY.
- The gate fails unless the EVIDENCE block printed in full and at least one step ran. The scripts are covered by `tests/unit/test_dev_bootstrap_gates.py`.

## Pull requests

- One topic per PR. Smaller diffs land faster.
- Use `git commit -s` to sign off (Developer Certificate of Origin). The project is licensed under BUSL-1.1, which auto-converts to Apache-2.0 on the Change Date (2030-05-10). Contributions are accepted under the project license.
- User-visible changes (new command, new flag, exit-code semantics, output format) need a `CHANGELOG.md` entry under `[Unreleased]`.
- Command/flag changes must regenerate the CLI reference: run `python -m typer decoy.__main__ utils docs --name decoy --output docs/cli-reference.md` and commit it. The `tests/unit/test_cli_surface.py` guard fails CI if you forget, so the command surface cannot change without its docs.
- If a change is more than one PR, file an Issue describing the plan first.

## Code style

`ruff` for lint + format. Run `ruff check src/ tests/` and `ruff format src/ tests/` before pushing.

## Where things live

See [`CODEMAP.md`](CODEMAP.md) for the package layout.
