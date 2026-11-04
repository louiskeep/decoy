Status: record

# X0a CLI registry record (part 1b: register the CLI allowlists)

Slice X0a, CLI half, part 1b. Branch `feat/x0a-gate-reg`, stacked on `feat/x0a-gate`
(part 1a, `2026-11-04-x0a-cli-build.md`). Merges after part 1a.

## Environment

- Base: CLI `origin/main` `cffab75c0175974bb33aa9d5e86444d31ff870d5`; parent `feat/x0a-gate` `35d38eb`.
- Same venv as part 1a (`bootstrap.sh` RESULT OK against `requirements-dev.lock`), Python 3.10.20.
- Port source: engine `tests/sentry/_baseline_sources.py`, `test_baseline_registry.py` (#379 `78132c57`).

## What changed

- `tests/sentry/_baseline_sources.py`: one `Source`, `engine-internal-allow`, over
  `test_engine_internal_boundary.py` `ALLOWLIST`. `InCode` takes a key function
  (`file::symbol`) and a reason function. The module is registered in `sys.modules` before it
  runs, because its dataclass resolves string annotations through it (the engine loader did not
  need this). `NOT_A_LIST_CONSTS` names `_ALLOWED_EVENT_FIELDS` and `_GUARD_EXCEPTIONS`.
- `tests/sentry/test_baseline_registry.py`: mirror test (both directions), no source-less row,
  unregistered-reader scan over every `SENTRIES` file (the three `tests/unit` sentries included),
  seeded negatives, and a check that each `NOT_A_LIST_CONSTS` entry still exists.
- `tests/sentry/baselines/engine-internal-allow.json` and its registry row: generated once by
  `python tests/sentry/_baseline_sources.py --write-initial`, each entry carrying its own
  `AllowedInternal.reason` (shortest 68 chars).
- `test_sentry_manifest.py`: `SENTRIES` gains `tests/sentry/test_baseline_registry.py`.
- After review r1 (section below): two more sources, `root-help-omitted` and
  `readme-table-omitted`, over `tests/unit/test_surface_docs_consistency.py`
  `_ROOT_HELP_OMITTED` and `_README_TABLE_OMITTED`, read with `ast.literal_eval` (that module
  builds the live Typer app on import). The scan's name regex gains `OMIT`, and
  `frozenset`/`set`/`tuple`/`list` calls count as collections. `--write-initial` now writes only
  sources with no baseline and never rewrites one.

## Scan result on main

First pass (r0, handoff regex `ALLOW|EXEMPT|WAIVER|BASELINE|EXCEPTIONS`, literal collections only):
`ALLOWLIST`, `_ALLOWED_EVENT_FIELDS`, `_GUARD_EXCEPTIONS`. That pass was incomplete: it missed two
`frozenset(...)` allowlists named `*_OMITTED` (review r1 F1). With the widened scan the 20 manifest
files hold exactly five: `ALLOWLIST`, `_ROOT_HELP_OMITTED`, `_README_TABLE_OMITTED` (registered),
`_ALLOWED_EVENT_FIELDS` and `_GUARD_EXCEPTIONS` (not lists). Committed `.json`/`.toml` under
`tests/` and `docs/` read by a sentry: none beyond the registered baselines. The orchestrator ruled
on 2026-11-04 to register both `*_OMITTED` lists.

## Red and green

Red on commit `bfe7734` (tests, no row, no baseline):
`test_source_matches_its_registered_baseline[engine-internal-allow]` (`sentry not registered`) and
`test_registry_has_no_source_less_sentry`: `2 failed, 9 passed`. Green on `76f5f8c`: the three
named files `41 passed`.

Seeded (each applied on the head, run, reverted):

| Seed | Red |
|---|---|
| 11th `AllowedInternal` (`_REGISTRY.values`) | mirror: `live entries missing from the baseline` |
| same key also added to the JSON | mirror green; `ratchet_check.py --base HEAD` exit 1: `baseline gained key(s) not in the merge base: cli/cockpit.py::decoy_engine.validators._registry._REGISTRY.values` |
| `NEW_ALLOWLIST = {"a": "b"}` in `test_notify_redaction.py` | `test_no_sentry_reads_an_unregistered_baseline` |
| one key deleted from the JSON only | mirror: `live entries missing from the baseline` |

The growth seed uses `--base HEAD` because against `origin/main` the whole registry is a first
inventory; growth is caught by the gate once this part is on main.

## Mutations

| Mechanism | Mutation | Result |
|---|---|---|
| mirror, stale direction | assert only `live - recorded` | seed "entry removed from code only" passes (survives); restored: `stale baseline entries` |
| mirror, missing direction | assert only `recorded - live` | seed "key deleted from JSON only" passes (survives); restored: `live entries missing` |
| manifest scan scope | scan only `tests/sentry/` | seeded `X_ALLOWLIST = {"a": 1}` in `tests/unit/test_cli_surface.py` passes (survives); restored: red naming `test_cli_surface.py: constant X_ALLOWLIST` |

Drift: the handoff pairs "assert only `live - recorded`" with the delete-from-JSON seed, but that
direction still catches it. Each direction was mutated against the seed it alone catches.

## Review r1 and fixes

Cold review `reviews/x0a-cli-r1` @ `00c2c31`: GO-WITH-FIXES, 1 MEDIUM (F1), 6 LOW V2-LOG.

| Finding | Class | Fix commit | Pinning test (red first on `35c3df6`) |
|---|---|---|---|
| F1 scan missed `*_OMITTED` frozenset allowlists | 8, overclaimed evidence | `b6eeb94` | `test_seeded_unregistered_constants_are_caught` (6 call or `OMIT` seeds red), mirror tests for the two new sources |
| F2 placeholder rule hidden by `MIN_REASON` | 8, weak test | `35c3df6` | `test_empty_or_placeholder_reason_fails[todo...........]`, `[N/A!!!!!!!!!!!!]` (red under `PLACEHOLDERS = frozenset()`) |
| F4 scan scope and shape pinned only by seeds | 8, weak test | `35c3df6` | `test_scan_reaches_the_tests_unit_sentries`; tuple and set seeds |
| F5 `created_in` stripped before `--slice` | 9, port drift | `b6eeb94` | `test_padded_created_in_does_not_match_the_slice` |

Red run on `35c3df6`: `10 failed, 46 passed`, all `AssertionError` (seeds `assert [] == [...]`,
mirror `sentry not registered`, padded slice `assert 0 == 1`). Green on `b6eeb94`: `56 passed`.
F2 and F5 touch part 1a files (`_ratchet.py`, `test_ratchet_check.py`) by orchestrator instruction.
F3, F6, F7 stay V2-LOG (below).

Mutations on the fixes (each red, reverted): drop `OMIT` from the regex (`_NEW_OMITTED` seed);
calls not collections (6 seeds); `is_coll` Dict only (tuple, set seeds); scan `tests/sentry` only
(`test_scan_reaches_the_tests_unit_sentries`); `PLACEHOLDERS = frozenset()` (2 params); strip
`created_in` again (padded test); blank check without strip (`test_missing_created_in_fails[  ]`).
Seed `info` added to `_ROOT_HELP_OMITTED`: mirror red; also in the JSON: `ratchet_check.py --base
HEAD` exit 1, `root-help-omitted: baseline gained key(s) not in the merge base: info`.

## First inventory

`root-help-omitted` (3 keys): `doctor`, `schema`, `upgrade`. `readme-table-omitted` (7 keys):
`doctor`, `fit`, `info`, `schema`, `subset`, `unmask`, `upgrade`. Both `created_in = "X0a"`,
hand-checked against the source literals; one written reason per list (the source has none per
entry).

`engine-internal-allow`, `created_in = "X0a"`, 10 keys, hand-checked one for one against `ALLOWLIST`:

```
ci/engine_logging.py::decoy_engine.internal.logging
ci/engine_logging.py::decoy_engine.internal.logging._LOGGER_INSTANCE
ci/engine_logging.py::decoy_engine.internal.logging.get_logger
cli/cockpit.py::decoy_engine.checksums._KNOWN_SCHEMES
cli/cockpit.py::decoy_engine.execution._strategies.SCALAR_HANDLERS
cli/cockpit.py::decoy_engine.execution._strategies.SCALAR_HANDLERS.get
cli/cockpit.py::decoy_engine.execution._strategies.SCALAR_HANDLERS.items
cli/cockpit.py::decoy_engine.execution._strategies.SCALAR_HANDLERS.keys
cli/cockpit.py::decoy_engine.validators._registry._REGISTRY
cli/cockpit.py::decoy_engine.validators._registry._REGISTRY.keys
```

`.venv/bin/python scripts/dev/ratchet_check.py --slice X0a` on `b6eeb94`, exit 0:

```
ratchet: engine-internal-allow: 10 key(s) in tests/sentry/baselines/engine-internal-allow.json
ratchet: engine-internal-allow: first inventory, 10 key(s), review required
ratchet: readme-table-omitted: 7 key(s) in tests/sentry/baselines/readme-table-omitted.json
ratchet: readme-table-omitted: first inventory, 7 key(s), review required
ratchet: root-help-omitted: 3 key(s) in tests/sentry/baselines/root-help-omitted.json
ratchet: root-help-omitted: first inventory, 3 key(s), review required
```

## Gates

`bash scripts/dev/gates.sh --keep-going --baseline` on `b6eeb94`: env PASS, ruff PASS, format
SKIP, mypy SKIP, sentry PASS (383; baseline 327), tests PASS (56; baseline SKIP). Failing ids:
branch 0, baseline 0, branch-only 0. The sentry step log carries the six ratchet lines above.
Earlier head `76f5f8c`: sentry 368, tests 41, failing ids 0 / 0 / 0.
`tests/unit/test_dev_bootstrap_gates.py`: 15 passed. `ruff check src tests scripts/dev/ratchet_check.py`
and `ruff format --check` on the touched files: pass. `bash -n scripts/dev/gates.sh`: ok.

## Files vs allowed list

The six allowed files, plus by orchestrator ruling the two new baselines
(`root-help-omitted.json`, `readme-table-omitted.json`) and, for F2 and F5, the part 1a files
`tests/sentry/_ratchet.py` and `tests/sentry/test_ratchet_check.py`. Nothing else
(`git diff --name-only feat/x0a-gate...HEAD`).

## Size

`git diff --shortstat feat/x0a-gate...HEAD`, records excluded: 9 files, 467 insertions, 4 deletions.
Generated and excluded: the three baseline JSON files (36, 27, 15 lines) and the 12 registry-row
lines, so 381 hand-written lines plus this record.

## Named limits

- The ratchet sees `file::symbol` keys only for `engine-internal-allow`. Raising an existing
  entry's `count` is not a new key; the boundary sentry's exact-count check and review hold it.
- The reader scan is name- and shape-based: an allowlist named outside
  `ALLOW|EXEMPT|WAIVER|BASELINE|EXCEPTIONS|OMIT`, built by a call other than
  `frozenset`/`set`/`tuple`/`list` (for example `dict(...)` or a comprehension), or a data path
  built from fragments, is not seen.
- The two `*_OMITTED` baselines carry one reason per list; the per-command rationale lives in the
  comments beside the source literal.

## V2-LOG

- F3 (r1): no automated test pins that the `gates.sh` sentry step calls `ratchet_check.py` and
  fails on its exit; a manual gate run shows it does (part 1a record).
- F6 (r1): under bash 3.2 `set -u`, unchanged `scripts/dev/gates.sh` lines 71 (`mapfile`), 83
  (empty `PYTEST_ARGS`), 88 (empty `MYPY_ARGS`) and 93 (empty `PATHS`) abort before the sentry
  step. The part 1a record named only line 83. The later CLI CI part owns these lines.
- F7 (r1): the gate never passes `--slice`, so the slice rule fires only on a manual run.

## Not verified

- AT-CI3, AT-CI4: out of scope.
- bash 3.2: no binary on this host (the r1 reviewer could not build one either).
- Full suite: `gates.sh` is a trigger, deferred to orchestrator T3.
