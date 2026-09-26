"""Fail-closed guard for decoy-cli's optional extras.

CLI install DX (2026-09-25): `pip install decoy-cli` stays lean by default;
cloud connectors, NER, and ML weight are opt-in via extras (cloud/ner/ml,
see pyproject.toml). A pipeline that exercises one of these paths without
the extra installed should fail with the exact install line, not a raw
ImportError/ModuleNotFoundError -- generalizes the DE-02 keyprovider probe
in run.py (see _MaskSecretUsageError) into one reusable translator any
command's exception-handling boundary can call.

`vault` is a separate, pyproject-only compatibility alias:
`cryptography` is a base engine dependency (Task 5.2, FF1 needs its AES-256
backend unconditionally), so `_MODULE_TO_EXTRA` has no vault entry --
cryptography can never fail to import for lack of the extra, and a real
import failure there is always a defect, never a missing-extra fix.
"""

from __future__ import annotations

# Maps the underlying import name (as ImportError.name reports it, or a
# leading dotted prefix of it) to the decoy-cli extra that installs it.
# Only these names get the friendly "add it with" treatment; any other
# ImportError is a real defect and the caller should leave it unclassified
# (EXIT_RUNTIME), not swallow it as a usage error.
_MODULE_TO_EXTRA: dict[str, str] = {
    "boto3": "cloud",
    "botocore": "cloud",
    "google.cloud": "cloud",
    "spacy": "ner",
    "sklearn": "ml",
    "lightgbm": "ml",
}


class MissingExtraError(Exception):
    """A pipeline step needs an optional extra that is not installed;
    user-fixable (exits EXIT_USAGE) by running the printed install line.

    `extra` is the machine-readable extra name (e.g. "cloud", "ner") so a
    caller can put it on the `--json` error envelope without
    parsing the message text.
    """

    def __init__(self, message: str, *, extra: str) -> None:
        self.extra = extra
        super().__init__(f"[missing_extra] {message}")


def _match_extra(module_name: str) -> str | None:
    """Match `module_name` against _MODULE_TO_EXTRA, trying the full dotted
    name first and then progressively shorter leading prefixes (so
    "google.cloud.storage" matches the "google.cloud" entry)."""
    parts = module_name.split(".")
    for end in range(len(parts), 0, -1):
        candidate = ".".join(parts[:end])
        extra = _MODULE_TO_EXTRA.get(candidate)
        if extra is not None:
            return extra
    return None


def _failed_name_is_probed(probed: str, failed: str) -> bool:
    """True when `failed` (a ModuleNotFoundError's `.name`) is `probed`
    itself or a leading dotted prefix of it -- confirms the import that
    actually failed is the package we probed for, not an unrelated module
    missing somewhere inside its own dependency chain (a real ABI
    error or corrupted install must not be mislabeled as a missing
    extra)."""
    return probed == failed or probed.startswith(failed + ".")


def require_extra(module_name: str, *, why: str) -> None:
    """Probe that `module_name` (an extra's underlying package) is
    importable; raise MissingExtraError with the exact install line if not.

    `why` is a short clause naming the capability, e.g. "PII autodetect
    (NER)"; it prefixes the message, and the install-line shape stays fixed
    so scripts can grep for `pip install decoy-cli[`.

    Only a `ModuleNotFoundError` for `module_name` itself (or a leading
    prefix of it, e.g. "google" when "google.cloud.storage" was probed and
    the `google` namespace package is entirely absent) is treated as a
    missing extra; any other `ImportError` -- including a `ModuleNotFoundError`
    for an unrelated transitive import -- is a real defect and propagates
    unclassified.
    """
    try:
        __import__(module_name)
    except ModuleNotFoundError as exc:
        if not exc.name or not _failed_name_is_probed(module_name, exc.name):
            raise
        extra = _match_extra(module_name)
        if extra is None:
            raise
        raise MissingExtraError(
            f"{why} isn't installed. Add it with:  pip install decoy-cli[{extra}]",
            extra=extra,
        ) from exc


# Maps a pipeline source/target `type` discriminator (see
# decoy_engine.config._sources / ._targets) to the module its lazy import
# probes for. Only s3/gcs need this; local `file` sources need nothing.
_CLOUD_ENDPOINT_MODULE: dict[str, str] = {
    "s3": "boto3",
    "gcs": "google.cloud.storage",
}


class UnsupportedCloudEndpointError(Exception):
    """Neither `decoy run` nor `decoy.mask()` can read from or write to
    S3/GCS yet: the local I/O helpers both entry points share
    (`_load_sources_from_config` / `_write_mask_outputs` /
    `_run_chunked_mask` in run.py) only handle a `path`-typed source or
    target, and the engine's own S3/GCS connectors are never reached from
    either. Without this check a cloud source/target would be silently
    skipped: the run reports success with the masked output for that table
    never written anywhere. Raised up front, before execution, so the
    failure is loud and typed instead of a false success that drops data."""


def check_cloud_endpoints_supported(config_dict: dict) -> None:
    """Refuse a pipeline whose `sources`/`targets` declare an s3 or gcs
    endpoint: `decoy run` and `decoy.mask()` cannot execute against one yet
    (see UnsupportedCloudEndpointError). This is separate from
    check_cloud_endpoints below (which only checks the SDK is installed)
    because that check stays useful for a command that validates a config
    without executing it; execution needs both checks, this one first.
    """
    for endpoint_kind, endpoints in (
        ("source", config_dict.get("sources") or {}),
        ("target", config_dict.get("targets") or {}),
    ):
        if not isinstance(endpoints, dict):
            continue
        for table_name, endpoint in endpoints.items():
            endpoint_type = endpoint.get("type") if isinstance(endpoint, dict) else None
            if endpoint_type in _CLOUD_ENDPOINT_MODULE:
                raise UnsupportedCloudEndpointError(
                    f"the {endpoint_type} {endpoint_kind} '{table_name}' cannot run through "
                    "`decoy run` or `decoy.mask()` yet: cloud sources/targets are not wired "
                    "into the CLI's execution path, only local files are. Installing [cloud] "
                    "adds the SDK dependency but not I/O support for either; tracked as a "
                    "known gap."
                )


def check_cloud_endpoints(config_dict: dict) -> None:
    """Scan a validated pipeline config's `sources`/`targets` for an s3 or
    gcs entry and, if found, probe for the matching SDK up front -- before
    the engine attempts any network call -- so a missing `[cloud]` extra
    fails with the install line rather than however boto3/google-cloud-
    storage's own absence happens to surface deep in a source/sink fetch.

    No-op when every source/target is local (the common case, and the only
    one a lean `pip install decoy-cli` needs to support).
    """
    for endpoint_kind, endpoints in (
        ("source", config_dict.get("sources") or {}),
        ("target", config_dict.get("targets") or {}),
    ):
        for endpoint in endpoints.values():
            module = _CLOUD_ENDPOINT_MODULE.get(endpoint.get("type"))
            if module is not None:
                require_extra(
                    module,
                    why=f"the {endpoint['type']} {endpoint_kind} connector this pipeline uses",
                )


def translate_ner_unavailable(exc: Exception) -> MissingExtraError | None:
    """Rewrite the engine's NerUnavailableError (text_mask/text_redact
    `ner`, storm/ner.py ensure_ner_available) to point at decoy-cli's own
    pass-through `[ner]` extra instead of `decoy-engine[ner]` -- correct for
    someone who installed decoy-engine directly, not for a decoy-cli user.

    `compile_plan` (`plan/_checks.py`) catches `NerUnavailableError` at
    plan-compile time and re-raises it wrapped in `PlanCompileError(code=
    exc.code, ...)`, so a config-time NER failure never reaches the CLI as
    a raw `NerUnavailableError` -- it arrives as a `PlanCompileError`
    carrying the same code. Both shapes are checked here.

    Only the "spaCy itself is absent" code is rewritten
    (`ner_spacy_not_installed`); `ner_model_not_installed` means spaCy IS
    present and the fix is `spacy download <model>`, not an extra, so the
    engine's own message is left alone. Returns None for anything else
    (including neither exception type, or an engine build old enough that
    the class import itself fails), so the caller treats it as
    unclassified rather than mislabeling it.
    """
    try:
        from decoy_engine.plan import PlanCompileError
        from decoy_engine.storm.ner import NerUnavailableError
    except ImportError:
        return None
    if not isinstance(exc, (NerUnavailableError, PlanCompileError)):
        return None
    if getattr(exc, "code", None) != "ner_spacy_not_installed":
        return None
    return MissingExtraError(
        "PII autodetect (NER) isn't installed. Add it with:  pip install decoy-cli[ner] "
        "(then run: python -m spacy download en_core_web_sm)",
        extra="ner",
    )


def plan_compile_error_fields(exc: Exception) -> tuple[str, str]:
    """Return the (code, message) pair a caller should render for a
    `PlanCompileError`, rewriting the `ner_spacy_not_installed` case to
    point at decoy-cli's own `[ner]` extra via `translate_ner_unavailable`.

    Every command that displays a `PlanCompileError` (`validate`,
    `preflight`, `plan`, `compile`, `unmask`, `vault info`, `subset`; `run`
    calls `translate_ner_unavailable` directly) renders `exc.code`/
    `exc.message` at its own call site. The NER rewrite has to reach all of
    them, so this is the single shared boundary each calls instead of
    duplicating the check. Callers print the result with Rich markup off:
    both the code (often shown as `[code]`) and the rewritten install line
    contain brackets Rich would parse as tags. Returns the untranslated
    `(exc.code, exc.message)` for anything else.
    """
    translated = translate_ner_unavailable(exc)
    if translated is None:
        return exc.code, exc.message  # type: ignore[attr-defined]
    message = str(translated).removeprefix("[missing_extra] ")
    return "missing_extra", message


def translate_missing_extra(exc: ImportError) -> MissingExtraError | None:
    """If `exc` is a ModuleNotFoundError for a known optional-extra module
    (raised lazily from inside the engine, e.g. a pipeline step that
    targets S3/GCS or uses NER), return the friendly MissingExtraError to
    raise instead. Returns None for any other ImportError -- including a
    plain ImportError that isn't a ModuleNotFoundError -- so the caller
    leaves it unclassified rather than mislabeling a real defect as a
    usage error.
    """
    if not isinstance(exc, ModuleNotFoundError):
        return None
    name = exc.name
    if not name:
        return None
    if name == "google":
        # The `google` namespace package itself absent (not just
        # google-cloud-storage): exc.name reports the shell package, which
        # is never a _MODULE_TO_EXTRA key on its own.
        name = "google.cloud"
    extra = _match_extra(name)
    if extra is None:
        return None
    return MissingExtraError(
        "this pipeline needs an optional capability that isn't installed. "
        f"Add it with:  pip install decoy-cli[{extra}]",
        extra=extra,
    )
