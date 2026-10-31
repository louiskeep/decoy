# CLI needs from the engine's public API

For the orchestrator. The CLI must not import `decoy_engine.internal.*` or engine `_private`
names (sentry: `tests/sentry/test_engine_internal_boundary.py`). Checked against the pinned
engine (0.15.1, `requirements-dev.lock`) and engine `origin/main` (545d913): none of the
following has a public equivalent. Each is allowlisted in the sentry until it does.

Resolved without an engine change: `completers.py` now uses `decoy_engine.list_generate_faker_providers()`
(identical 258 names to the old internal call).

| # | CLI site | Reads today (private) | Public symbol the engine should export | Why |
|---|----------|-----------------------|----------------------------------------|-----|
| 1 | `ci/engine_logging.py` | `internal.logging.get_logger`, `internal.logging._LOGGER_INSTANCE` | `decoy_engine.silence_engine_logging() -> contextlib.AbstractContextManager[None]` (or `configure_logging(file: str \| None, console: bool, level: str)` plus reset) | `decoy ci` must create no `logs/decoy_engine.log` and must restore prior logger state; the engine's file sink is built on first logger use with a cwd-relative default |
| 2 | `cli/cockpit.py` (`list/show strategy`) | `execution._strategies.SCALAR_HANDLERS` | `decoy_engine.list_mask_strategies() -> dict[str, type]` (name to handler class) | CLI lists and describes registered mask strategies from the live registry |
| 3 | `cli/cockpit.py` (`list checksums`) | `checksums._KNOWN_SCHEMES` | `decoy_engine.checksums.list_schemes() -> tuple[str, ...]` (sorted) | CLI lists supported checksum schemes |
| 4 | `cli/cockpit.py` (`list validators`) | `validators._registry._REGISTRY` | `decoy_engine.validators.list_validators() -> tuple[str, ...]` (sorted) | CLI lists registered job-level validators |

Signatures are proposals; any public, documented, stable shape that returns the same data
works. When one lands and the CLI repins, delete the matching `ALLOWLIST` entry (the sentry
fails on a stale entry, so the removal cannot be forgotten).
