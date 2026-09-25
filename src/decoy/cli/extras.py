"""Fail-closed guard for decoy-cli's optional extras.

CLI install DX (2026-09-25): `pip install decoy-cli` stays lean by default;
cloud connectors, NER, ML, and vault weight are opt-in via extras
(cloud/ner/ml/vault, see pyproject.toml). A pipeline that exercises one of
these paths without the extra installed should fail with the exact install
line, not a raw ImportError/ModuleNotFoundError -- generalizes the DE-02
keyprovider probe in run.py (see _MaskSecretUsageError) into one reusable
translator any command's exception-handling boundary can call.
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
    "cryptography": "vault",
}


class MissingExtraError(Exception):
    """A pipeline step needs an optional extra that is not installed;
    user-fixable (exits EXIT_USAGE) by running the printed install line."""


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


def require_extra(module_name: str, *, why: str) -> None:
    """Probe that `module_name` (an extra's underlying package) is
    importable; raise MissingExtraError with the exact install line if not.

    `why` is a short clause naming the capability, e.g. "PII autodetect
    (NER)"; it prefixes the message, and the install-line shape stays fixed
    so scripts can grep for `pip install decoy-cli[`.
    """
    try:
        __import__(module_name)
    except ImportError as exc:
        extra = _match_extra(module_name)
        if extra is None:
            raise
        raise MissingExtraError(
            f"{why} isn't installed. Add it with:  pip install decoy-cli[{extra}]"
        ) from exc


# Maps a pipeline source/target `type` discriminator (see
# decoy_engine.config._sources / ._targets) to the module its lazy import
# probes for. Only s3/gcs need this; local `file` sources need nothing.
_CLOUD_ENDPOINT_MODULE: dict[str, str] = {
    "s3": "boto3",
    "gcs": "google.cloud.storage",
}


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
                require_extra(module, why=f"this pipeline has a {endpoint['type']} {endpoint_kind}")


def translate_ner_unavailable(exc: Exception) -> MissingExtraError | None:
    """Rewrite the engine's NerUnavailableError (text_mask/text_redact
    `ner`, storm/ner.py ensure_ner_available) to point at decoy-cli's own
    pass-through `[ner]` extra instead of `decoy-engine[ner]` -- correct for
    someone who installed decoy-engine directly, not for a decoy-cli user.

    Only the "spaCy itself is absent" code is rewritten
    (`ner_spacy_not_installed`); `ner_model_not_installed` means spaCy IS
    present and the fix is `spacy download <model>`, not an extra, so the
    engine's own message is left alone. Returns None for anything else
    (including a non-NerUnavailableError, or an engine build old enough
    that the class import itself fails), so the caller treats it as
    unclassified rather than mislabeling it.
    """
    try:
        from decoy_engine.storm.ner import NerUnavailableError
    except ImportError:
        return None
    if not isinstance(exc, NerUnavailableError):
        return None
    if getattr(exc, "code", None) != "ner_spacy_not_installed":
        return None
    return MissingExtraError(
        "PII autodetect (NER) isn't installed. Add it with:  pip install decoy-cli[ner]"
    )


def translate_missing_extra(exc: ImportError) -> MissingExtraError | None:
    """If `exc` is an ImportError for a known optional-extra module (raised
    lazily from inside the engine, e.g. a pipeline step that targets S3/GCS
    or uses NER), return the friendly MissingExtraError to raise instead.
    Returns None for any other ImportError, so the caller leaves it
    unclassified rather than mislabeling a real defect as a usage error.
    """
    name = getattr(exc, "name", None)
    if not name:
        return None
    extra = _match_extra(name)
    if extra is None:
        return None
    return MissingExtraError(
        "this pipeline needs an optional capability that isn't installed. "
        f"Add it with:  pip install decoy-cli[{extra}]"
    )
