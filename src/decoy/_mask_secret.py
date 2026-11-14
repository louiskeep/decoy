"""The one mask-secret path the CLI surfaces share.

`--mask-secret REF` (or `mask_secret=`) fills the same `global_settings.mask_secret_ref` slot the
YAML can set; both set is a usage error, keyed on presence, so one secret source is chosen
explicitly. A command admits the secret once through the engine's public `admit_mask_key` inside
an `AdmissionScope` (closed on every exit) and hands that one provider to every engine entry it
calls, so a run and its vault see one read and one key. With a provider the engine does not read
the ref again (`secret_providers.admit_mask_key`: "a programmatic key_provider wins").

No implicit source: nothing here reads an environment variable, a default file or generates key
bytes; the ref names the secret and the engine resolves it. Errors never echo the ref value.

A `file:` secret must be owner-only. The CLI opens it first, checks the mode on the open
descriptor (`fstat`, after the symlink is followed, so the target is what is checked), and hands
the engine that same file as `file:/dev/fd/N`: a swap of the path after the check changes
nothing, because the engine reads the inode that was checked (the check-then-use shape OpenSSH
uses for private keys: `sshkey_perm_ok` on the opened descriptor). The engine (>=0.18.0) runs the
same owner-only check on the descriptor it reads (`secret_file_permissions_unsafe`), so a mode
widened after this check is still refused, with the same constant text. The CLI's check also
refuses a directory or any non-regular file with the owner-only text; the engine's calls a
directory a missing secret. Skipped on Windows, where POSIX mode bits do not describe who can
read the file.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, NoReturn

# The schemes the shape rule lets through. `vault` parses in the engine; the CLI registers no
# provider for it, so the engine refuses it with `secret_provider_unknown` instead of the CLI
# calling it malformed.
_REF_SCHEMES = frozenset({"env", "file", "vault"})

BOTH_SET = (
    "--mask-secret was passed but the YAML already sets "
    "global_settings.mask_secret_ref. Set the masking "
    "secret in exactly one place: drop --mask-secret, or "
    "remove mask_secret_ref from the config."
)
INVALID = (
    "Invalid global_settings.mask_secret_ref or --mask-secret: expected an "
    "'env:NAME' or 'file:/PATH' reference to a >=32-byte secret. It "
    "is a REFERENCE, never the raw secret. "
    "See: decoy explain keys."
)
FLAG_HELP = (
    "Reference to the mask secret the run used: 'env:NAME' or 'file:/PATH' (a >=32-byte "
    "secret; an owner-only file, never the raw value). Sets global_settings.mask_secret_ref "
    "for this command; an error if the YAML also sets it. See: decoy explain keys."
)


class MaskSecretFlagError(Exception):
    """A usage error from `apply_mask_secret` (exits EXIT_USAGE); its text holds no value."""


def mask_secret_ref_problem(raw: object) -> str | None:
    """The one shape rule for a mask secret reference: `INVALID`, or None when it is well formed.

    The engine's own parser decides what a reference is (`secret_providers.parse_ref`, which
    lower-cases the scheme, so `ENV:NAME` passes); this adds the CLI's provider set. The text
    names no part of `raw`, and a non-string is refused without being formatted.
    """
    from decoy_engine.secret_providers import parse_ref

    if not isinstance(raw, str):
        return INVALID
    scheme: str | None = None
    try:
        scheme = parse_ref(raw).scheme
    except Exception:
        scheme = None  # the engine's refusal is the bare `bad_secret_ref`; only the verdict is kept
    return None if scheme in _REF_SCHEMES else INVALID


def apply_mask_secret(
    config_dict: dict,
    flag: str | None,
    *,
    error: type[Exception] = MaskSecretFlagError,
    both_set: str = BOTH_SET,
) -> None:
    """Inject `flag` into the config, then check the effective ref's shape.

    Presence, not truthiness: a YAML `mask_secret_ref: ""` is a configured slot the flag must
    not override, and an empty ref is refused rather than read as "no secret". A non-mapping
    `global_settings` (unvalidated YAML on `unmask` / `report vault`) is left to the engine's
    own refusal; there is no slot to put a flag into."""
    settings = config_dict.get("global_settings")
    if settings is not None and not isinstance(settings, dict):
        if flag is not None:
            raise error(INVALID)
        return
    if flag is not None:
        if (settings or {}).get("mask_secret_ref") is not None:
            raise error(both_set)
        if settings is None:
            settings = config_dict["global_settings"] = {}
        settings["mask_secret_ref"] = flag
    ref = (config_dict.get("global_settings") or {}).get("mask_secret_ref")
    problem = None if ref is None else mask_secret_ref_problem(ref)
    if problem is not None:
        raise error(problem)


UNSAFE_CODE = "secret_file_permissions_unsafe"
# Any group or other bit. The owner's own bits are the owner's business (0400, 0600, 0700 pass).
_GROUP_OR_OTHER = 0o077


def _refuse_unsafe() -> NoReturn:
    from decoy_engine.keyprovider import MaskSecretError

    # Each surface prints the constant text registered for this code, never this message.
    raise MaskSecretError(code=UNSAFE_CODE, message="the mask secret file is not owner-only")


def _refuse_missing() -> NoReturn:
    from decoy_engine.keyprovider import MissingMaskSecret

    raise MissingMaskSecret("the referenced mask secret file could not be opened")


def _open_checked(locator: str) -> int:
    """Open the secret file and check the OPEN descriptor: a regular file, owner-only.

    Opening follows a symlink, so the target's mode is checked. O_NONBLOCK keeps a FIFO from
    hanging the open; anything that is not a regular file (a directory, a FIFO, a device) is
    refused with the same owner-only text."""
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    flags |= getattr(os, "O_NOCTTY", 0)
    # Raised outside the handlers: an OSError's text and filename carry the path.
    fd = mode = None
    try:
        fd = os.open(locator, flags)
        mode = os.fstat(fd).st_mode
    except OSError:
        pass
    if fd is None or mode is None:
        if fd is not None:
            os.close(fd)
        _refuse_missing()
    if not stat.S_ISREG(mode) or mode & _GROUP_OR_OTHER:
        os.close(fd)
        _refuse_unsafe()
    return fd


@contextmanager
def _checked_secret_file(config_dict: dict) -> Iterator[dict]:
    """`config_dict` with a `file:` ref replaced by the checked descriptor, open for the body.

    Only a mapping `global_settings` holding a `file:` string is touched; anything else (no ref,
    `env:`, a non-mapping `global_settings` from unvalidated YAML) passes through unchanged to
    the engine's own handling."""
    settings = config_dict.get("global_settings")
    ref = settings.get("mask_secret_ref") if isinstance(settings, dict) else None
    if (
        os.name == "nt"
        or not isinstance(settings, dict)
        or not isinstance(ref, str)
        or ref[: len("file:")].lower() != "file:"  # the engine reads the scheme in any case
    ):
        yield config_dict
        return
    from decoy_engine.secret_providers import parse_ref

    rest = ref[len("file:") :]
    locator = parse_ref(ref).locator  # a malformed ref is the engine's bad_secret_ref
    if not rest.startswith(locator):
        _refuse_missing()
    fd = _open_checked(locator)
    try:
        checked = f"file:/dev/fd/{fd}{rest[len(locator) :]}"
        yield {**config_dict, "global_settings": {**settings, "mask_secret_ref": checked}}
    finally:
        os.close(fd)


@contextmanager
def admitted_key_provider(config_dict: dict) -> Iterator[Any]:
    """The command's one admitted provider; None when nothing is keyed and no ref is set.

    Every surface that admits the secret (`run`, `tokenize`, `unmask`, `report vault`,
    `decoy.mask()`) comes through here and hands the engine this provider, so the engine never
    reads the ref itself. The checked file is closed once admission has read it."""
    from decoy_engine.secret_providers import AdmissionScope, admit_mask_key

    with AdmissionScope() as scope:
        with _checked_secret_file(config_dict) as checked:
            admitted = scope.adopt(admit_mask_key(checked))
        yield admitted.key_provider
