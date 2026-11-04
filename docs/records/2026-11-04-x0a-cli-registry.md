Status: record

# X0a CLI registry record (part 1b: register the CLI allowlist)

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

## Scan result on main

Constants matching `ALLOW|EXEMPT|WAIVER|BASELINE|EXCEPTIONS` across the 19 manifest files: exactly
`ALLOWLIST` (registered), `_ALLOWED_EVENT_FIELDS` and `_GUARD_EXCEPTIONS` (not lists). Committed
`.json`/`.toml` under `tests/` and `docs/`: three, none read by a sentry. Precondition 3 holds.

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

## First inventory

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

`.venv/bin/python scripts/dev/ratchet_check.py --slice X0a` on `76f5f8c`, exit 0:

```
ratchet: engine-internal-allow: 10 key(s) in tests/sentry/baselines/engine-internal-allow.json
ratchet: engine-internal-allow: first inventory, 10 key(s), review required
```

## Gates

`bash scripts/dev/gates.sh --keep-going --baseline` on `76f5f8c`: env PASS, ruff PASS, format
SKIP, mypy SKIP, sentry PASS (368; baseline 327), tests PASS (41; baseline SKIP). Failing ids:
branch 0, baseline 0, branch-only 0. The sentry step log carries the two ratchet lines above.
`tests/unit/test_dev_bootstrap_gates.py`: 15 passed. `ruff check src tests scripts/dev/ratchet_check.py`: pass.

## Files vs allowed list

Exactly the six allowed files (`git diff --name-only feat/x0a-gate...HEAD`).

## Size

`git diff --shortstat feat/x0a-gate...HEAD` before this record: 5 files, 312 insertions. Generated
and excluded: `tests/sentry/baselines/engine-internal-allow.json` (36 lines) and the 4-line
registry row, so 272 hand-written lines.

## Named limits

- The ratchet sees `file::symbol` keys only. Raising an existing entry's `count` is not a new
  key; the boundary sentry's exact-count check and review hold it.
- The reader scan is name- and literal-based: an allowlist named outside the regex, or a data
  path built from fragments, is not seen.

## V2-LOG

None.

## Not verified

- AT-CI3, AT-CI4: out of scope.
- bash 3.2: no binary on this host.
- Full suite: `gates.sh` is a trigger, deferred to orchestrator T3.
