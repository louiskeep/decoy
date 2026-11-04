# Dennis review: x0a-cli r2

Verdict: GO. 0 BLOCKER / 0 HIGH / 0 MEDIUM / 4 LOW. V1 0 / V2-LOG 4.

Mode B. Repo decoy. HEAD 090785ab8f0a5f77b1de27b6926d652fb63f50d0. BASE cffab75c0175974bb33aa9d5e86444d31ff870d5. Reviewed on merged tree cffab75c0175974bb33aa9d5e86444d31ff870d5 + HEAD (scratch merge 06090ebb, tree e554772c, identical to HEAD's tree).
Main moved since BASE: 0 commits; overlapping files: none.
Review skills run: none (see "What I did NOT verify").

Summary. All four r1 fixes close at the root. Each has a test that I reproduced red on 35c3df6 with an assertion failure and green on HEAD. Every stated mutation goes red. No existing test was weakened. The two new inventories match the source literals and are read without importing `decoy`. `--write-initial` never rewrites an existing baseline. The widened scan finds nothing else unregistered. The port still differs from engine `_ratchet.py` only by the documented `created_in` and `--slice` rules. The new findings are all V2-LOG: the literal reader takes the first binding only, so a later rebinding can grow an `*_OMITTED` list past the ratchet; two scanner/reader properties are unpinned; `--write-initial` can append a duplicate row; and a 4-line size miscount.

## Findings

### F1. LOW, V2-LOG, class 2 (mirror pinned to the first source binding, not the live value)
Where: tests/sentry/_baseline_sources.py:49-64 (`_literal_constant` returns at :63 on the first top-level match), :86-89; tests/sentry/test_baseline_registry.py:71-79 (scan sees only collection-shaped values); docs/records/2026-11-04-x0a-cli-registry.md:157 (named limits).
What is wrong: the literal reader returns the first module-level binding of the constant. A later `X = X | {...}` or `X |= {...}` grows the list the sentry actually uses, but the mirror still sees the first literal. The scan does not flag the rebinding either, because a `BinOp` or `AugAssign` is not a collection shape. The ratchet sees no new key. So an `*_OMITTED` allowlist can grow with every gate green. The import-based reader used for `engine-internal-allow` would catch this. The record's named limits do not mention it. There is no product effect.
Evidence: on the merged tree I deleted the `decoy report show` row (README.md:116) and appended `_README_TABLE_OMITTED = _README_TABLE_OMITTED | {"report"}` after the literal in tests/unit/test_surface_docs_consistency.py. Then `pytest -q tests/sentry/test_baseline_registry.py tests/sentry/test_ratchet_check.py tests/unit/test_surface_docs_consistency.py` gave `61 passed`, and `ratchet_check.py --slice X0a` exited 0. I restored both files and the tree was clean.
Fix: in literal mode, fail when the constant has more than one module-level binding (`Assign`, `AnnAssign`, `AugAssign`), or compare the literal with the imported value in a subprocess. Add a seeded rebinding case that is red without the guard, and name the limit in the record.

### F2. LOW, V2-LOG, class 2 (shape and no-import properties unpinned)
Where: tests/sentry/test_baseline_registry.py:58 (`ast.List` in `_is_collection`), :137-149 (seeds); tests/sentry/_baseline_sources.py:134, :139 (`literal=True`).
What is wrong: no seed is a bare list literal, so dropping `ast.List` from the scanner survives. Nothing pins that the two new sources are read without importing the module, so turning `literal=True` off survives. That property is the stated reason for the new reader. It holds today, and I verified it directly, but no test holds it.
Evidence: mutation O1 (`(ast.Dict, ast.Tuple, ast.Set)`) gave `50 passed`. Mutation O4 (drop `literal=True` on root-help-omitted) gave `50 passed`. A direct check with a meta-path hook that blocks `decoy` imports read `['doctor','schema','upgrade']` and the 7 README keys, and `decoy` was not in `sys.modules` afterwards.
Fix: add a `NEW_ALLOWLIST = ["a"]` seed. Assert `src.keys.literal` for both `*_OMITTED` sources, or run `items()` under an import block in a test.

### F3. LOW, V2-LOG, class 14 (re-run path appends a duplicate registry row)
Where: tests/sentry/_baseline_sources.py:163-182.
What is wrong: when a registered baseline file is missing, `write_initial` regenerates it and appends a second `[[sentry]]` row for an id that is already registered. The ratchet flags the duplicate, so this fails closed. It is still a wrong write.
Evidence: `rm tests/sentry/baselines/root-help-omitted.json; python tests/sentry/_baseline_sources.py --write-initial` exited 0 and added 4 lines to sentry_registry.toml. `ratchet_check.py` then printed `ratchet: FAIL registry: sentry id root-help-omitted appears twice`. I restored the files and the tree was clean. The other two baselines were not touched.
Fix: skip the row append when the id is already in the registry, or refuse when a registered baseline is missing.

### F4. LOW, V2-LOG, class 4 (evidence arithmetic)
Where: docs/records/2026-11-04-x0a-cli-registry.md:151.
What is wrong: the record says 381 hand-written lines. Numstat against 35d38ebd gives 189 + 164 + 20 + 3 + 1 = 377, with the 12 registry lines and 78 JSON lines excluded. The 467 total is correct. This is well under 800.
Evidence: `git diff --numstat 35d38ebd 090785ab`.
Fix: correct the figure to 377.

## Prior findings (mode B rounds 2-3 only)

- F1: closed. 35c3df6 tests reproduced red (6 call/`OMIT` seeds `assert [] == [...]`, mirror `sentry not registered`, `assert {'engine-internal-allow'} == ...`). b6eeb94 is green. Mutations M1, M2 and M3 are red. My census of the 20 manifest files finds no other unregistered allowlist.
- F2: closed. `PLACEHOLDERS = frozenset()` turns `[todo...........]` and `[N/A!!!!!!!!!!!!]` red. Both are at least 15 chars, so only the placeholder rule can fire.
- F4: closed. Scanning only tests/sentry is red (`test_scan_reaches_the_tests_unit_sentries`). Dict-only is red (tuple and set seeds). See new F2 for the list literal.
- F5: closed. A raw compare is in place (_ratchet.py:65). Re-adding the strip turns `test_padded_created_in_does_not_match_the_slice` red. Removing the strip from the blank check (:127) turns `test_missing_created_in_fails[  ]` red.
- F3, F6, F7: still open, ruled V2-LOG by the orchestrator and logged in the record. The F6 line anchors (gates.sh:71, :83, :88, :93) still point at the named code.

## FOCUS checks

- (a) See "Prior findings". The 35c3df6 red run gave `10 failed, 46 passed`, all `AssertionError`, as the record says.
- (b) Nothing was weakened. Every removed test line from 66194fab to HEAD is either moved or widened. The `NEW_ALLOWLIST = {"a": "b"}` constant seed is now param 1 of `test_seeded_unregistered_constants_are_caught` with the same assertion. The data-file seed is unchanged. The placeholder list is a superset. Only additions in test_ratchet_check.py.
- (c) `root-help-omitted` is {doctor, schema, upgrade} and `readme-table-omitted` is {doctor, fit, info, schema, subset, unmask, upgrade}. Both equal the frozenset literals at test_surface_docs_consistency.py:42 and :60. Reasons are 113 and 116 chars. `created_in` is "X0a". Both are read via `ast.literal_eval` with no `decoy` import (verified, see F2).
- (d) Holds. With all baselines present, the run exits 1 with `every source already has a baseline; nothing to write` and changes nothing. With one baseline deleted, it writes only that one and leaves the other two untouched (see F3 for the row).
- (e) Holds. An AST census of every module-level collection, call, comprehension or BinOp in the 20 files shows `*_OMITTED`, `ALLOWLIST`, `_ALLOWED_EVENT_FIELDS` and `_GUARD_EXCEPTIONS` as the only allowlist-shaped constants. `_DEFAULT_COMMAND_FLAGS`, `_NEEDS_VAULT`, `SPAN_CALLS` and similar are pinned surfaces or fixtures, not bypass lists. The function-local `allow*` names are fixtures.
- (f) Holds. Against engine origin/main a749172e, `diff` of `_ratchet.py` and `ratchet_check.py` shows only the docstring, the `created_in` capture (:62-65), the blank check (:127-128), the `--slice` compare (:153-156), the `set()` style change and the dropped `noqa`. The blank check strips, which is stricter than the platform's `not created_in`, and SPEC asks for a non-empty string.
- (g) The evidence claims I checked are true: the red run, green 56, gate counts 383/56/327 with 0/0/0 failing ids, the six ratchet lines, the five-constant scan result, every listed mutation, the `info` seed (mirror `live entries missing`, then `ratchet_check.py --base HEAD` FAIL `baseline gained key(s) not in the merge base: info`), the file list and 467 insertions. Exceptions: the size arithmetic (F4) and the missing rebinding limit (F1).

## What I ran

All from ~/review/x0a-cli-r2/merged with DECOY_VENV=~/review/x0a-cli-r2/venv. `ulimit -n 65536 2>/dev/null || ulimit -n "$(ulimit -Hn)"` ran first in each shell (65536 is not permitted here, so the hard limit applied). One venv, built from the merged tree's requirements-dev.lock. The branch and baseline runs both used it.

- STEP ZERO: `git rev-parse origin/feat/x0a-gate-reg` = 090785ab (match). BASE exists and is an ancestor. MAIN = cffab75c (= BASE). The report branch was absent. The push dry-run was OK. I read SPEC and DEFECT-CATALOG (handoffs/queue), EVIDENCE and the r1 report. decoy-engine and decoy-platform were cloned read-only.
- `git merge-tree --write-tree $MAIN $HEAD`: no conflict, tree e554772c.
- `bash scripts/dev/bootstrap.sh`: exit 0, `RESULT:     OK, environment matches requirements-dev.lock and the engine pins`.
- `timeout 1800 bash scripts/dev/gates.sh --keep-going --baseline`: exit 0. Branch: env PASS, ruff PASS, format SKIP, mypy SKIP, sentry PASS passed=383, tests PASS passed=56. Baseline: ruff PASS, sentry PASS passed=327, tests SKIP. `(branch=0 baseline=0 branch-only=0)`.
- `python -m pytest -q -rfE -p no:cacheprovider tests/sentry/test_ratchet_check.py tests/sentry/test_sentry_manifest.py tests/sentry/test_baseline_registry.py`: `56 passed`.
- `scripts/dev/ratchet_check.py --slice X0a`: exit 0, six lines as in the record. `--slice S0`: exit 1, three `created_in 'X0a' is not slice 'S0'`.
- Red reproduction: I checked out the 35c3df6 versions of `_ratchet.py`, `sentry_registry.toml` and the two test files, removed the two new JSONs, and ran the named tests: `10 failed, 46 passed`, all assertion failures. Restored, clean.
- Mutations (each applied, run on test_ratchet_check.py and test_baseline_registry.py, restored with `git checkout --`, then `git diff --quiet HEAD` exit 0):
  - M1 drop `OMIT` from LIST_NAME: red (1, `_NEW_OMITTED` seed).
  - M2 calls not collections: red (6).
  - M3 `_is_collection` Dict only: red (2, tuple and set).
  - M4 scan tests/sentry only: red (`test_scan_reaches_the_tests_unit_sentries`).
  - M5 `PLACEHOLDERS = frozenset()`: red (2).
  - M6 strip `created_in` again: red (padded test).
  - M7 blank check without strip: red (`[  ]`).
  - O1 (own) drop `ast.List`: SURVIVED, 50 passed (F2).
  - O2 (own) `_covered` keyed by full path: red (`test_no_sentry_reads_an_unregistered_baseline`).
  - O3 (own) never unwrap the call in `_literal_constant`: red (both new mirror params).
  - O4 (own) `literal=True` off for root-help: SURVIVED, 50 passed (F2).
  - O5 (own seed) rebinding `_README_TABLE_OMITTED | {"report"}` plus README row removed: SURVIVED, 61 passed, ratchet exit 0 (F1).
  - O6 (own) `--write-initial` on a full tree, then with one baseline deleted (F3).
- Commits (9, BASE..HEAD): every subject is `type(scope): summary`, at most 67 chars, lowercase, no period. The final line is `cam` on each, and there are no trailers. The em-dash grep (`LC_ALL=C.UTF-8`) over the diff and the messages gave 0 and 0.
- Size: `git diff --numstat 35d38ebd 090785ab` (F4). Largest .py is 240 lines.

## What I did NOT verify

- Review skills: `/review` is not installed. `code-review` and `security-review` are listed, but they operate on the session working directory, which is the builder's worktree /home/user/decoy. This review must not touch it, so I did not run them. No Codex, by design.
- Full suite (T3): out of scope.
- Postgres and native companion tests: none are selected. The companion is not installed.
- bash 3.2: no binary on this box (r1 F6 stays V2-LOG).
- AT-CI3 and AT-CI4: out of scope per SPEC.
- I did not run the gate separately on the intermediate heads 35c3df6 or b6eeb94. HEAD differs from b6eeb94 only in the record.
