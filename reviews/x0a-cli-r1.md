# Dennis review: x0a-cli r1

Verdict: GO-WITH-FIXES. 0 BLOCKER / 0 HIGH / 1 MEDIUM / 6 LOW. V1 1 / V2-LOG 6.

Mode B. Repo decoy. HEAD 66194fab0b897e5733a56ef7fe47a893dbd40a25. BASE cffab75c0175974bb33aa9d5e86444d31ff870d5. Reviewed on merged tree cffab75c0175974bb33aa9d5e86444d31ff870d5 + HEAD (scratch merge c200d541, tree identical to HEAD's tree 01df8b6a).
Main moved since BASE: 0 commits; overlapping files: none.
Review skills run: none (see "What I did NOT verify").

Summary. The port is faithful. `tests/sentry/_ratchet.py` and `scripts/dev/ratchet_check.py` differ from engine origin/main (78132c57) only by the two `created_in` rules, `--slice`, and dropped `noqa` comments. Every engine AT-CI0 case has a CLI twin. Every stated mutation went red for the right reason. The gate is green with no new failing id. Commits, em-dashes and file scope are clean. One spec-level gap: two allowlists in a newly manifested sentry are neither registered nor declared non-lists, and the scanner cannot see their shape.

## Findings

### F1. MEDIUM, V1 (process), class 4 (false current-state claim) and catalog class 8 (overclaimed evidence)
Where: tests/unit/test_surface_docs_consistency.py:42 `_ROOT_HELP_OMITTED`, :60 `_README_TABLE_OMITTED`; tests/sentry/test_baseline_registry.py:29 (`LIST_NAME`), :70-72 (`is_coll`), :1-6 (docstring); docs/records/2026-11-04-x0a-cli-registry.md "Scan result on main".
What is wrong: SPEC goal 3 says every committed allowlist a CLI sentry reads is registered and mirrored. SPEC precondition 3 says to stop if the scan finds an allowlist-shaped constant beyond the three named ones. Part 1a added `tests/unit/test_surface_docs_consistency.py` to the manifest. That sentry holds two module-level `frozenset({...})` lists that it calls "the allowlist" in its own failure messages (lines 37, 212, 217, 222, 255, 260, 265). They are not in `SOURCES` and not in `NOT_A_LIST_CONSTS`. The scan misses them for two reasons: the name regex `ALLOW|EXEMPT|WAIVER|BASELINE|EXCEPTIONS` does not match `OMITTED`, and `is_coll` accepts only `Dict/Tuple/List/Set` literals, so any `frozenset(...)` value is invisible. The second blind spot means a new allowlist written in the style this repo already uses passes the scan. The record's "exactly ALLOWLIST, _ALLOWED_EVENT_FIELDS and _GUARD_EXCEPTIONS ... Precondition 3 holds" is true only for the regex. The test docstring "fails when any file in the SENTRIES manifest ... holds an allowlist-shaped constant" is false. The record's named limit covers names outside the regex but not the `frozenset(...)` value shape. The SPEC remeasure table also missed these two constants, so this is partly a SPEC inventory gap. No product effect.
Evidence:
- My own seed, appended `NEW_ALLOWLIST = frozenset({"bypass::site"})` to tests/sentry/test_notify_redaction.py, then `venv/bin/python -m pytest -q -rfE -p no:cacheprovider tests/sentry/test_baseline_registry.py` gave `5 passed` (survived). Control seed `NEW_ALLOWLIST = {"bypass::site": "x"}` gave `1 failed` (`test_no_sentry_reads_an_unregistered_baseline`). Restored, tree clean.
- I listed every module-level constant in the 20 manifest files with an AST walk. The two `_*_OMITTED` constants are the only allowlist-shaped ones beyond the three named in SPEC. (`_REFLECT`, `BANNED_NAMES`, `DEAD_STRINGS`, `_BANNED_GLYPHS` are denylists or rule data.)
Fix: the owner rules on whether the two `_*_OMITTED` lists are bypass lists. If they are, register them as `Source` rows (key = command name, reason from the adjacent comment or a written reason of at least 15 chars) with a `created_in` of X0a. If they are not, add them to `NOT_A_LIST_CONSTS` with a reason. In both cases, widen the scanner: treat a `Call` to `frozenset/set/tuple/list/dict` whose argument is a collection literal as a collection, add `OMIT` to `LIST_NAME`, and add a seeded `frozenset` case to `test_seeded_unregistered_readers_are_caught` that is red before the widening. Correct the record line and the docstring.

## V2-LOG

### F2. LOW, V2-LOG, class 2 (mutation hidden by a second rule)
Where: tests/sentry/_ratchet.py:29, :77; tests/sentry/test_ratchet_check.py:97.
What is wrong: the placeholder rule is never pinned. Every placeholder param (`todo`, `TBD.`, `FIXME`) is under `MIN_REASON`, so the length rule fires and hides it. A reachable case such as `"todo..........."` (15 chars, strips to `todo`) relies only on `PLACEHOLDERS`. The same gap exists in the engine test.
Evidence: mutation `PLACEHOLDERS = frozenset()` gave `30 passed` (survived).
Fix: add a param of at least `MIN_REASON` chars that strips to a placeholder, for example `"todo" + "." * 11`.

### F3. LOW, V2-LOG, class 2 (gate wiring pinned only by hand)
Where: scripts/dev/gates.sh:91.
What is wrong: no automated test pins that the sentry step calls `ratchet_check.py` or fails on its exit code. `test_sentry_manifest.py` reads only `SENTRY_PATHS` and `PYTEST_ARGS`. `test_dev_bootstrap_gates.py` runs `--steps tests` only.
Evidence: mutation `|| exit 1` to `|| true` gave `56 passed` (survived), and removing the call gave `56 passed` (survived), over test_ratchet_check.py, test_sentry_manifest.py, test_baseline_registry.py and tests/unit/test_dev_bootstrap_gates.py. A manual gate run confirms the wiring is load-bearing: with an untracked unregistered `tests/sentry/baselines/scratch.json`, `gates.sh --steps sentry` gives `[sentry] FAIL(rc=1)` with `ratchet: FAIL tests/sentry/baselines/scratch.json: baseline file is not registered`. With the call removed it gives `[sentry] PASS passed=368`.
Fix: add a test that runs `gates.sh --steps sentry` in a seeded clone holding an unregistered baseline and asserts FAIL. The harness in test_dev_bootstrap_gates.py already seeds clones.

### F4. LOW, V2-LOG, class 2 (scan scope and shape pinned only by seeds)
Where: tests/sentry/test_baseline_registry.py:102-108, :70-72.
What is wrong: narrowing `_manifest_sources` to `tests/sentry/` or narrowing `is_coll` to `Dict` both pass on the committed tree. The tests/unit coverage that FOCUS (e) asks about holds today, but no test asserts it.
Evidence: mutation P3 (scan only `tests/sentry/`) gave `5 passed`. With seed `X_ALLOWLIST = {"a": 1}` in tests/unit/test_cli_surface.py it is red unmutated and green mutated. Mutation P4 (`is_coll` Dict only) gave `5 passed`.
Fix: assert that `_manifest_sources()` holds the three tests/unit basenames, and add tuple and set seeds to the seeded test.

### F5. LOW, V2-LOG, class 9 (port drift)
Where: tests/sentry/_ratchet.py:65, :153.
What is wrong: the CLI strips `created_in` before the `--slice` compare. Platform `_ratchet.py` does not strip, so `" X0a "` passes `--slice X0a` on the CLI but fails on the platform. This is harmless, but it does not match the platform rule the SPEC ports.
Fix: compare the raw string, or reject padded values as a finding.

### F6. LOW, V2-LOG, class 4 (incomplete limit disclosure)
Where: scripts/dev/gates.sh:71 (`mapfile`, bash 4+), :83 (`"${PYTEST_ARGS[@]}"` empty), :88 (`"${MYPY_ARGS[@]}"` empty), :93 (`"${PATHS[@]}"` empty), all unchanged lines.
What is wrong: the new sentry line 91 uses the 3.2-safe idiom `${a[@]+"${a[@]}"}`. Under bash 3.2 with `set -u`, though, the script aborts before it reaches the sentry step: line 83 aborts on the empty `PYTEST_ARGS` and line 88 on the empty `MYPY_ARGS`. When no paths are given, `mapfile` does not exist in bash 3.2. The record's V2-LOG names only line 83. The SPEC forbids editing these lines, so this is for the later CI part.
Fix: the later CI part makes these lines 3.2-safe, and the records name all four.

### F7. LOW, V2-LOG, class 15 (design note)
Where: scripts/dev/gates.sh:91.
What is wrong: the gate never passes `--slice`, so the `created_in == slice` rule fires only when someone runs `ratchet_check.py --slice` by hand. The SPEC calls the flag optional, so this is as specified. As wired, though, a first inventory with a wrong `created_in` passes the gate.
Fix: the later CI part passes the slice name (for example from the branch) or documents that the check is manual.

## Prior findings (mode B rounds 2-3 only)

None (round 1).

## FOCUS checks

- (a) Port: `diff` against engine origin/main 78132c57 `tests/sentry/_ratchet.py` and `scripts/dev/ratchet_check.py` shows only the `created_in` rule (lines 62-66, 127-128), the `--slice` rule (153-156, script line 35 and 48), comments and dropped `noqa`. The 15 engine test functions all have twins. The CLI is stricter on `test_baseline_gaining_a_key_fails` (count-equal swap), `test_renamed_baseline_with_extra_key_fails` (new id, split rule, exact message), and the reason, unregistered-file and first-inventory needles. The engine's rename case kept id `a` on a new path with an extra key. The CLI covers that as `test_moved_baseline_for_a_kept_id_fails` without the extra key. The `moved` finding fires independently of keys (line 140-142, `continue`), so nothing is lost. The CLI adds cases for registry path outside the dir, duplicate id, slice, kept sentry not held to the slice, missing `created_in` (4 params) and no merge base. Holds.
- (b) `created_in`: missing, `""`, `"  "` and `7` are all findings (verified, and mutations E6 and O2 red). `--slice`: a new id with no removed ids is checked (E5 red). I also ran `ratchet_check.py --slice S0` on the head and got exit 1 with `created_in 'X0a' is not slice 'S0'`. During a split the new ids are not held to the slice, as the SPEC says. Holds (see F5, F7).
- (c) Line 91 runs with `cd "$tree"`. It skips only when `scripts/dev/ratchet_check.py` is not a file, as the baseline worktree run showed (`[sentry] PASS passed=327`, no ratchet lines). If the helper is missing but the script is present, the step fails closed (import error, exit 1). bash 3.2 safety of line 91 holds by idiom only. I did not run it (see F6 and Not verified).
- (d) `PYTEST_ARGS=()` parses to no marker, `PYTEST_ARGS=(-m 'not slow')` to `not slow`, and the live gate collection passes no `-m`. Holds. The `[^)]*` limit is disclosed.
- (e) The scan does cover the three tests/unit files (seed S3 red). It finds nothing beyond the three constants, but the reason is narrow matching, not an absence of allowlists. See F1.
- (f) `git diff --name-only` per part matches the two allowed tables exactly (1a: 8 files; 1b: 6 files). No existing sentry or test file is edited except the one-line `SENTRIES` addition in 1b. gates.sh changes only the `SENTRY_PATHS` block and the sentry step plus their comments. Holds.

## What I ran

All from ~/review/x0a-cli-r1/merged with DECOY_VENV=~/review/x0a-cli-r1/venv, `ulimit -n 65536` first. One venv, built from the merged tree's requirements-dev.lock. Branch and baseline ran in it.

- STEP ZERO: `git rev-parse origin/feat/x0a-gate-reg` = 66194fab (match). BASE exists and is an ancestor. MAIN = cffab75c (= BASE). The report branch was absent. The push dry-run was OK. SPEC, DEFECT-CATALOG and both records were read. decoy-engine (origin/main 78132c57) and decoy-platform were cloned read-only.
- `git merge-tree --write-tree $MAIN $HEAD`: no conflict, tree 01df8b6a (same as HEAD).
- `DECOY_VENV=... bash scripts/dev/bootstrap.sh`: exit 0, `RESULT:     OK, environment matches requirements-dev.lock and the engine pins` (Python 3.10.20, native companion not installed).
- `timeout 1800 bash scripts/dev/gates.sh --keep-going --baseline`: exit 0. Branch: env PASS, ruff PASS, format SKIP, mypy SKIP, sentry PASS passed=368, tests PASS passed=41 (3 changed test files). Baseline: ruff PASS, sentry PASS passed=327, tests SKIP. `FAILING TEST IDS (branch=0 baseline=0 branch-only=0)`. The branch sentry log starts with `ratchet: engine-internal-allow: first inventory, 10 key(s), review required`.
- `venv/bin/python -m pytest -q -rfE -p no:cacheprovider tests/sentry/test_ratchet_check.py tests/sentry/test_sentry_manifest.py tests/sentry/test_baseline_registry.py`: `41 passed`.
- `venv/bin/python -m pytest -q -rfE -p no:cacheprovider tests/unit/test_dev_bootstrap_gates.py`: `15 passed`.
- `venv/bin/python scripts/dev/ratchet_check.py --slice X0a`: exit 0, the two lines match the record. `--slice S0`: exit 1.
- `ruff check src tests scripts/dev/ratchet_check.py`: All checks passed. `ruff format --check` on the 6 new .py files: already formatted. `bash -n scripts/dev/gates.sh`: ok.
- Red for the right reason, AT-CI1: checked out BASE `scripts/dev/gates.sh`, then ran test_sentry_manifest.py. `test_gates_sentry_paths_cover_every_sentry` failed with `Left contains 3 more items, first extra item: 'tests/unit/test_cli_surface.py'`, and the same assertion failed in `test_removing_a_sentry_path_is_detected` and `test_gates_step_collects_every_sentry`. Assertion reds. Restored, clean. AT-CI0 red as recorded is "can't open file ratchet_check.py", which the SPEC accepts for a new-script test. I did not re-run it on e922e0d.
- Commits (6): every subject is `type(scope): summary`, at most 72 chars, lowercase, no period, and the final line is exactly `cam`, with no trailers. Em-dash grep over the diff and the messages gave 0 and 0.
- Size: part 1a `git diff --shortstat cffab75 35d38ebd` gave 8 files, +671/-2. Part 1b `35d38ebd 66194fab` gave 6 files, +433 (JSON 36 included). Largest new .py file: 221 lines.
- Mutations (each applied, run, `git checkout --`, then `git diff --quiet HEAD` exit 0 every time):
  - E1 `_ratchet.py` growth by count, test_ratchet_check.py: red, `test_baseline_gaining_a_key_fails`.
  - E2 skip split union: red, rename, replaced and split cases (3).
  - E3 drop on-disk scan: red, `test_new_baseline_without_registry_entry_fails`.
  - E4 `MIN_REASON = 0`: red, `[]`, `[   ]` and `[too short]`.
  - E5 ignore `slice_name`: red, `test_first_inventory_created_in_must_match_slice`.
  - E6 drop `created_in` check: red, 4 `test_missing_created_in_fails` params.
  - O1 (own) `PLACEHOLDERS = frozenset()`: SURVIVED, 30 passed (F2).
  - O2 (own) no strip on `created_in`: red, `[  ]`.
  - O3 (own) split new ids treated as first inventory: red (4).
  - O4 (own) drop baseline-dir check: red, `test_registry_path_outside_baseline_dir_fails`.
  - O5 (own) drop duplicate-id check: red, `test_duplicate_registry_id_fails`.
  - O6 (own) drop sentry_id match: red, `test_baseline_id_must_match_registry_id`.
  - O7 (own) gates.sh `|| exit 1` to `|| true`: SURVIVED, 56 passed (F3).
  - O8 (own) gates.sh ratchet call removed: SURVIVED, 56 passed (F3). The manual gate run is red with the call and green without it (see F3).
  - P1 mirror stale direction removed: survives clean (5 passed), as designed.
  - P2 mirror missing direction removed: with seed S1 (key deleted from JSON) red unmutated, SURVIVED mutated, which matches the record's drift note.
  - P3 scan scope tests/sentry only: with seed S3 (`X_ALLOWLIST` in tests/unit/test_cli_surface.py) red unmutated, SURVIVED mutated, as the record says (F4).
  - P4 (own) `is_coll` Dict only: survives (F4).
  - P5 (own) drop data-file check: red, `test_seeded_unregistered_readers_are_caught`.
  - S4 (own seed) `NEW_ALLOWLIST = frozenset({...})`: not caught (F1). S5 dict control: caught.

## What I did NOT verify

- bash 3.2: no binary on this box. My attempt to build bash 3.2.57 from GNU source was denied by the sandbox permission policy. Line 91 is judged by idiom only. See F6 for unchanged lines that abort before it under 3.2.
- Review skills (`code-review`, `security-review`) are listed but were not run. They target the session working directory, which is the builder's worktree /home/user/decoy, and this review must not touch it. No Codex run, by design.
- Full suite (T3): out of scope. `gates.sh` is a full-suite trigger, deferred to the orchestrator.
- Postgres and native companion tests: none are selected here. The companion is not installed.
- I did not re-run the part 1a head (35d38ebd) gate separately. The merged tree is the stack top, which contains it.
- AT-CI3 and AT-CI4: out of scope per SPEC.
- Function-local allowlists: I listed module-level constants only, plus a name grep for local `allow`-style names (only test fixtures found).
