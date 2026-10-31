Status: record (2026-10-31). Survey only. No code, test, lock or baseline was changed. This report carries no authority; the orchestrator re-verifies.

# Main health audit: decoy CLI (repo `decoy`), `origin/main` d28fae25

## 1. Verdict

| Python | Verdict | unit+sentry | e2e | ruff check | ruff format --check | type check |
|---|---|---|---|---|---|---|
| 3.10.20 (uv-managed, the lock profile) | main is RED | 2 failed, 812 passed | 29 failed, 897 passed, 5 skipped | pass | 83 files would reformat (not a CI gate) | none pinned |
| 3.11.18 (system) | main is RED | 814 passed | 29 failed, 897 passed, 5 skipped | not rerun (Python-independent) | same | none pinned |
| 3.12.3 (system) | main is RED | 814 passed, 7 warnings | 29 failed, 897 passed, 5 skipped, 52 warnings | not rerun | same | none pinned |

All 31 reds on 3.10 reproduce alone and three times each (93 of 93 isolated runs fail, section 6). None is a flake. Two classes:

- **Group A, R1-a (29 e2e on every Python): REAL REGRESSION, already owned.** The CLI calls engine symbols that engine 0.15.1 (the pin and the lock) deleted. A repin alone does not fix it (section 4).
- **Group B (2 unit, 3.10 only): ENVIRONMENT.** Two distribution tests copy the running interpreter into a nested venv; that layout cannot start when the interpreter is a uv-managed Python 3.10 build (section 3.2).

## 2. Environment

Clean venvs built from `requirements-dev.lock` only (63 pins, hashes), CLI installed editable with `--no-deps` on top, exactly as `scripts/dev/bootstrap.sh` does. No optional extra is installed: `decoy_engine_native` absent, `boto3` (cloud) absent, `spacy` (ner) absent. Tests ran as `root` (uid 0) on Ubuntu 24.04.5, Linux 6.18, x86_64, uv 0.11.32. One test runner at a time; disk checked before each run (27 to 28 GB free, floor 4 GB); every temporary worktree removed (`git worktree list` shows only the checkout).

```
$ DECOY_VENV=$S/venv310 bash scripts/dev/bootstrap.sh
python:     3.10.20 (ci.yml expects 3.10.x)
lock:       requirements-dev.lock sha256 a12cd32a84127dcf (fresh)
decoy-engine installed 0.15.1     pin 0.15.1     OK
             commit fd51be10673225d81a8c000d460b0172112b26ac (lock pins fd51be10...; ci.yml installs @v0.15.1)
full env:   matches requirements-dev.lock exactly (63 pins)
native:     companion NOT installed; engine expects decoy-native-abi-3 (the CLI does not need it)
RESULT:     OK, environment matches requirements-dev.lock and the engine pins
```

3.11 and 3.12 venvs: `uv venv --python 3.1x`, `uv pip sync requirements-dev.lock`, `uv pip install --no-deps -e .`; `scripts/dev/_lock_verify.py` prints `matches requirements-dev.lock exactly (63 pins)` for both. Same package set on all three: decoy-engine 0.15.1 (fd51be10), duckdb 1.5.6, pyarrow 25.0.1, polars 1.44.2, pandas 2.3.3, numpy 2.2.6, typer 0.26.8, pytest 9.2.0, ruff 0.15.14, faker 40.23.0, cryptography 50.0.2, pydantic 2.14.2.

Commands (the `ci.yml` pytest and ruff jobs; CI passes no markers, so none were used):

```
pytest tests/unit tests/sentry --tb=short      # plus -p no:cacheprovider -rfE --junitxml
pytest tests/e2e --tb=short
ruff check src tests                           # ruff 0.15.14, the ci.yml pin
ruff format --check src tests                  # NOT in ci.yml (pyproject.toml [tool.ruff] comment)
```

Type check: `ci.yml` has no mypy or pyright job, no type checker is in `pyproject.toml` or the lock, and `scripts/dev/gates.sh` sets `MYPY_ARGS=()` so its mypy step reports SKIP (`CONTRIBUTING.md:40`). There is no pinned type check; I ran none rather than run an unpinned one.

The 5 e2e skips are intended: 4 need a real compiled `decoy-engine-native` companion, 1 (`test_unreadable_source_does_not_crash_preflight`) skips with reason "chmod 000 is bypassed by root". That root-only case already does the right thing.

## 3. Failures

### 3.1 Group A: `resolve_substrate` and the `substrate=` kwarg (29 e2e tests)

Category: REAL REGRESSION (API drift between the CLI and its pinned engine). Catalog class: 10 (frozen contract drift: the engine removed public symbols a consumer still imports), plus class 8 for the weeks it sat in the baseline. Known as R1-a.

Failure line for 13 tests (CLI exit 3 where 0 was expected): `AssertionError: error: cannot import name 'resolve_substrate' from 'decoy_engine.execution'`. 13 more fail on the same ImportError through a different assertion (`assert 3 == 0`, `assert 3 == 1`, `assert 'substrate' in ''`, `assert 'must be one of' in ''`, `assert ('invalid_substrate' in '' or 'must be one of' in '')`, `assert 1 == 0` on a CliRunner `Result ImportError(...)`, and a JSON error envelope carrying the same message for the route-indicator test). 2 fail on `TypeError: run_pipeline() got an unexpected keyword argument 'substrate'`. Same on 3.10, 3.11 and 3.12 (identical 29 ids, checked with diff).

| Test file (count) | Ids | Failing line |
|---|---|---|
| tests/e2e/test_run_chunked.py (8) | TestRunChunked::test_chunk_size_one, test_chunked_output_is_byte_identical_to_plain_run, test_deterministic_faker_chunked_matches_plain_run, test_explicit_pandas_substrate_matches_default_chunked, test_faker_without_pool_size_exits_usage, test_invalid_substrate_rejected, test_polars_substrate_rejected_as_removed, test_unsafe_strategy_exits_usage | :78 :72 :118 :127 :184 :170 :160 :86 |
| tests/e2e/test_run_chunked_parquet.py (7) | TestChunkedParquet::test_chunk_size_invariance, test_csv_source_parquet_target, test_empty_parquet_source_writes_valid_zero_row_file, test_nulls_preserved_through_parquet_stream, test_parquet_source_csv_target, test_parquet_to_parquet_value_parity_with_plain_run, test_same_chunk_size_is_byte_stable | :101 :158 :93 :144 :179 :170 :120 |
| tests/e2e/test_run_command.py (4) | TestSubstrateWarning::test_chunked_run_substrate_does_not_warn, test_plain_run_polars_substrate_rejected, test_plain_run_substrate_exits_zero_and_warns, test_plain_run_substrate_quiet_suppresses_warning | :434 :418 :407 :425 |
| tests/e2e/test_source_format_dispatch.py (4) | test_csv_declared_wins_over_suffix[True], test_csv_named_parquet_is_read_as_csv, test_parquet_declared_wins_over_suffix[True-data.pq], [True-data_no_ext] | :230 :243 :219 :219 |
| tests/e2e/test_run_native.py (2) | test_route_indicator_reports_resolved_substrate_for_chunked; test_no_native_stays_compatible_with_an_older_engine (TypeError) | :550; :415 |
| tests/e2e/test_mask_api_native.py (1) | test_mask_native_false_stays_compatible_with_an_older_engine (TypeError) | :212 |
| tests/e2e/test_duckdb_source.py (1) | test_duckdb_source_chunked | :120 |
| tests/e2e/test_run_mask_secret.py (1) | TestMaskSecretChunked::test_chunked_run_respects_mask_secret | :618 |
| tests/e2e/test_vault_cli.py (1) | TestVaultRoundTrip::test_chunked_run_writes_equivalent_vault | :96 |

Why: `src/decoy/cli/run.py:462` imports `resolve_substrate` whenever `--substrate` is given, and `run.py:1476` imports it unconditionally on every `--chunked` run, so every chunked test fails whether or not it passes `--substrate` (none is skipped). `src/decoy/api.py:515` forwards `substrate=` to `run_pipeline`, and the two "older engine" tests wrap the real `run_pipeline` with a fake that forwards `substrate=substrate` (`tests/e2e/test_mask_api_native.py:220`, `tests/e2e/test_run_native.py:409`), so those two hit the TypeError instead. The engine deleted the symbol on 2026-10-24 in d011deba ("E3a knob deletion"; its CHANGELOG: "`run_pipeline` no longer accepts `substrate`... `select_execution_adapter` takes only `fpe_chunk_count`; `resolve_substrate`, `VALID_SUBSTRATES` and the `DECOY_SUBSTRATE` environment variable are gone"). v0.15.1 (fd51be10, 2026-10-26) never had it: `git grep 'def resolve_substrate' fd51be10 -- src` prints nothing.

Introducing commits:

- The CLI has imported `resolve_substrate` since 44064ec (first-parent, 2026-07-24; S6 library API) and kept it through a08b1d8 (2026-10-01, "Reject the removed polars substrate"). dfe7b8d0 (2026-10-23, merged by 2d4496e) added the `api.py` `substrate=` forwarding and the three older-engine / route-indicator tests. test_duckdb_source_chunked was added in 7364ee9b (2026-10-24).
- d011deba (engine, 2026-10-24) is the day the CLI went red against engine `main`, which `ci.yml` installed at the time (`@main`, pyproject `>=0.7.0`).
- **92c3684a (2026-10-28, PR #64) is the first-parent CLI commit that made the red main's own**: it pinned `decoy-engine==0.15.1` and `ci.yml @v0.15.1`. d28fae25 (PR #70) then locked that engine commit, so the lock itself pins the red.

Bisect (4 representative tests on each of the 21 first-parent commits from d28fae2 back to 152d2bb of 2026-10-22, same 3.10 venv, each worktree's `src` on PYTHONPATH, import path verified per commit): every commit is red for `test_chunk_size_one`, `test_plain_run_substrate_exits_zero_and_warns` and `test_mask_native_false_stays_compatible_with_an_older_engine`; `test_duckdb_source_chunked` is red from its first commit 7364ee9 and absent before. Under the lock's engine there is no green CLI commit in the window, which is expected: the engine, not the CLI, changed.

Smallest correct fix (not made): in `run.py` delete both `resolve_substrate` imports and the `resolved_substrate` / `select_execution_adapter(substrate=...)` plumbing, in `api.py` stop forwarding `substrate=`, and retire the `--substrate` flag (the engine has one adapter; keep the "polars removed" usage error as a CLI-side constant if the flag stays one release). In the two older-engine tests remove `substrate` from the fake signature and its forwarding; no engine change is needed for this group.

Red-first test for the fix: a sentry that resolves every `decoy_engine` name the CLI imports (`grep -rho "from decoy_engine[.a-z_]* import [^)]*" src`) against the installed engine. It is red today on `resolve_substrate` and would have caught d011deba the day it landed.

### 3.2 Group B: copied interpreter in a nested venv (2 unit tests, 3.10 only)

Category: ENVIRONMENT (interpreter-layout assumption in the test helper). Catalog class: NEW (a test assumes the running interpreter survives being copied); nearest is class 8, since the red was accepted as baseline noise.

- `tests/unit/test_distribution.py::test_import_isolation_runs_bundle_decoy_and_blocks_hostile_cwd_and_pythonpath`, line 1221: `AssertionError: managed launcher failed to run the bundle decoy: Could not find platform independent libraries <prefix>` ... `ModuleNotFoundError: No module named 'encodings'`, `assert 1 == 0`.
- `tests/unit/test_distribution_acceptance.py::test_real_managed_interpreter_refuses_absent_then_abi_mismatched_companion`, line 405: same text, `assert 1 == 3`.

Both helpers (`_make_bundle_runtime`, test_distribution.py:1158, call at :1171; `_managed_python`, test_distribution_acceptance.py:365, call at :374) use `venv.EnvBuilder(with_pip=False).create(...)`. `EnvBuilder` defaults to `symlinks=False`, so it copies the interpreter binary into the new venv. The child then prints `sys.base_prefix = '/install'`, the compile-time prefix of the python-build-standalone build that uv installs, and dies before `site`. Proof by isolating the ingredients (each a `-I -c "import sys"` child):

```
uv-managed 3.10.20, nested in the test venv, symlinks=False -> fails (no Python frame)
uv-managed 3.10.20, nested, symlinks=True                   -> OK
/usr python 3.11.18 and 3.12.3, nested, either setting      -> OK
uv-managed 3.12.13, nested, symlinks=False                  -> OK (3.11+ getpath follows pyvenv.cfg home)
uv-managed 3.10.20, NOT nested, symlinks=False              -> OK
```

The red needs all three: Python 3.10, a uv-managed interpreter, and a venv created from inside another venv (the test venv). `scripts/dev/bootstrap.sh` builds exactly that (`uv venv --python 3.10`, which downloads a managed 3.10 on any machine without a system python3.10, for example Ubuntu 24.04). On the system 3.11 and 3.12 venvs both tests pass (814 passed each). GitHub's setup-python builds carry a real prefix, so these tests were green in hosted CI when it ran; the local gate is the only place they are red.

Introduced by 5ac7333b (2026-10-28, PR #66 "B-2 CLI-LAUNCH packaging"), which added both tests and both helpers. Bisect: red at 5ac7333, file absent at 1d9e030 and every earlier first-parent commit.

Counter-case checked: "it fails for a real reason on a clean machine" would mean the shipped launcher or bundle is broken. It is not: `packaging_tools/build_bundle.py:77` copies the whole interpreter tree (`shutil.copytree(real, dest, symlinks=True)`), so the real bundle's python sits next to its own `lib/`; only the test stand-in separates binary from stdlib. Product behavior is not affected. Second environment: the same two ids pass on 3.11 and 3.12 from the same lock.

What the tests should do: not skip, and not declare an extra (no extra is involved). Pass `symlinks=True` to both `EnvBuilder` calls; the child still reports the venv as `sys.prefix`, which is what `_managed_python` relies on, and the `-I` isolation property under test is unchanged. Two one-line test edits, no assertion weakened. A skip would hide the launcher isolation proof on exactly the interpreter the local gate uses.

### 3.3 `ruff format --check`: 83 of 188 files would reformat

Category: OTHER (documented non-gate). `pyproject.toml` `[tool.ruff]` says format is "intentionally NOT in the CI gate (45 files would reformat on first run)"; the count has drifted to 83. `gates.sh` sets `FORMAT_GATE=0` and reports SKIP. Not a red by the repo's own definition, but the number keeps growing. Fix: one formatting commit, then `FORMAT_GATE=1` and `ruff format --check` in the ruff job.

### 3.4 Type check

No pinned type checker exists (section 2). Nothing to report; adding one is a scope decision, not a fix.

### 3.5 Warnings (not failures)

3.12 only: `DeprecationWarning` from `decoy_engine/storm/types.py:262` (`datetime.utcnow()`), 7 in unit+sentry and 52 in e2e. Engine-side, harmless today, becomes an error only if `-W error` is ever added.

## 4. What in-flight work already fixes

Group A is R1-a, owned by the STORM engine release repin per the handoff. Finding: **a repin cannot fix it by itself.** No current engine ref defines `resolve_substrate`: `origin/main` (a6e5c25e) has zero definitions, no `v0.16.0` tag or `release/v0.16.0` branch exists on the remote, and every one of the 15 remote branches that still contains the function (`plan/a5-storm-rename`, `plan/substrate-route-coverage`, `feat/file-access-*`, `fix/faker-40-31-migration`, ...) is 51 to 126 commits behind main and predates d011deba. `run_pipeline` on main has no `substrate` parameter either. Whoever owns R1-a must change the CLI (section 3.1 fix), not only the pin. Group B is not covered by any item on `handoffs/queue` that I could find.

## 5. Fixes ordered by risk (lowest first)

1. Group B: `symlinks=True` in two test helpers. Test-only, two lines, no product path. Unblocks the local 3.10 gate on uv-managed Pythons.
2. Group A, CLI side: remove the `resolve_substrate` imports, the `substrate=` forwarding and the two stale fake signatures; add the import-surface sentry. Touches `run.py` and `api.py`; `--substrate` becomes a removed flag, a user-visible change that belongs with the R1-a owner.
3. Format gate: one reformat commit, then enable `ruff format --check` in `ci.yml` and `gates.sh`. Large diff, zero semantic change, highest merge-conflict risk with open branches.

## 6. Evidence

Full runs (`$S` is the scratch dir; logs kept there, not committed):

```
$ venv310/bin/python -m pytest tests/unit tests/sentry --tb=short -p no:cacheprovider -rfE
================== 2 failed, 812 passed in 177.69s (0:02:57) ===================
$ venv310/bin/python -m pytest tests/e2e --tb=short -p no:cacheprovider -rfE
============ 29 failed, 897 passed, 5 skipped in 240.55s (0:04:00) =============
$ venv311/bin/python -m pytest tests/unit tests/sentry ...
======================= 814 passed in 184.24s (0:03:04) ========================
$ venv311/bin/python -m pytest tests/e2e ...
============ 29 failed, 897 passed, 5 skipped in 235.60s (0:03:55) =============
$ venv312/bin/python -m pytest tests/unit tests/sentry ...
================= 814 passed, 7 warnings in 194.28s (0:03:14) ==================
$ venv312/bin/python -m pytest tests/e2e ...
====== 29 failed, 897 passed, 5 skipped, 52 warnings in 250.04s (0:04:10) ======
$ venv310/bin/ruff check src tests
All checks passed!
$ venv310/bin/ruff format --check src tests
83 files would be reformatted, 105 files already formatted
```

Reruns alone, then three times each (3.10):

```
$ venv310/bin/python -m pytest --tb=line -p no:cacheprovider -rfE <the 31 ids>
============================== 31 failed in 2.87s ==============================
$ for id in <31 ids>; do for i in 1 2 3; do pytest -q --tb=no "$id"; done; done
93 invocations, 93 rc=1, 0 rc=0
```

Bisect: 126 rows (21 first-parent commits x 6 ids), each run as `cd $WT && PYTHONPATH=$WT/src venv310/bin/python -m pytest -q --tb=line -rfE <id>` with `decoy.__file__` confirmed under `$WT/src` for every commit. Group A ids: rc=1 on all 21 commits where the file exists. Group B ids: rc=1 at 5ac7333 and the 6 commits after it, file absent at 1d9e030 and the 13 commits before.

Engine facts: `git -C decoy-engine grep -c 'def resolve_substrate' fd51be10 -- src` prints nothing; `git log -S resolve_substrate origin/main -- src` lists d011deba (delete, 2026-10-24) as the last change, both it and the prior add are ancestors of v0.15.1.

## 7. Not run or not verified

- No pinned type check exists, so none ran.
- The `fresh-install-smoke`, `ci-template-lint` and `certified-profile` jobs from `ci.yml` were not run (outside "full suite plus ruff and type check", and they need a wheel build and extra pins).
- Tests needing a compiled `decoy-engine-native` companion (4 skips) and the `cloud` / `ner` / `ml` extras were not exercised; the lock does not include those extras and CI does not install them.
- Non-root behavior was not tested; the one root-sensitive test already skips with a stated reason.
- Hosted CI is off (billing), so "green in hosted CI" for Group B is inferred from interpreter layout, not from a run.
- The engine history before 7795fc2f (2026-10-18) does not show `resolve_substrate` under `git log -S`, which looks like a squashed history; I did not chase when the engine first added the symbol.
