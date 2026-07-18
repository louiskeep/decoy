"""decoy - data masking and synthetic generation CLI, plus a thin library API.

The CLI is a thin terminal wrapper around decoy_engine. All data logic
lives in decoy_engine; this package only handles command parsing,
terminal UX, and forwarding work to the engine.

S6 (OSS-launch, 2026-07-18): `decoy.mask()` / `decoy.scan()` are the
library one-liner equivalents of `decoy run` / `decoy storm analyze`,
for `import decoy; decoy.mask(...)` without shelling out to the CLI. See
`decoy.api` for the implementation -- both wrap the exact same
decoy_engine entrypoints the CLI commands call.

`mask` / `scan` are resolved lazily (module `__getattr__`, PEP 562) so a
bare `import decoy` (e.g. just reading `__version__`) does not eagerly
pull in typer/pandas/pyarrow/decoy_engine.
"""

__version__ = "0.1.0"

_LAZY_API = frozenset({"mask", "scan", "MaskSecretConfigError", "ConfigValidationError"})


def __getattr__(name: str):
    if name in _LAZY_API:
        from decoy import api

        return getattr(api, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | _LAZY_API)
