"""Release signing: Ed25519 key custody + detached signatures (build host only).

Established methodology: Ed25519 via `cryptography`, the same scheme and key format as
the platform's output-passport / air-gapped-manifest signer
(`decoy-platform/api/passport/signing.py`, `api/crypto/signed_envelope.py`). No
hand-rolled crypto. The verify side ships in `decoy.distribution.signing`; this is the only
place a private key is ever read.

Key custody (config-secrets-and-supply-chain): the private key is sourced from the
environment, NEVER committed. ``DECOY_RELEASE_KEY_FILE`` points at a PEM/PKCS8 private
key (0600) held in the release secret store; ``DECOY_RELEASE_KEY_PEM`` may carry the
PEM inline for a CI secret. The public key is published in the repo
(`packaging_tools/release-key (public half shipped in the CLI)`) and on the site, and is what `install.sh` pins and
`decoy upgrade` trusts. Rotation: generate a new key, publish the new public key in a
signed release, and keep the old public key in a documented trust set for one
deprecation window so in-flight installers still verify prior releases.

Signatures are DETACHED and over the EXACT on-disk bytes of the file being signed, so
the identical signature verifies three ways: `openssl pkeyutl -verify -rawin` in the
shell installer, `decoy.distribution.signing.verify_detached` in `decoy upgrade`, and the
platform primitive on an auditor's host.
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

# Single source of truth for the public key: the one shipped in the CLI package
# (also what `decoy upgrade` pins). install.sh embeds a copy of the same key.
_PUBLIC_KEY_FILE = (
    Path(__file__).resolve().parents[1] / "src" / "decoy" / "distribution" / "release_key.pub.pem"
)


def load_private_key() -> Ed25519PrivateKey:
    """Load the release private key from the environment. Raises if neither source is
    set -- signing must never silently proceed without the real release key."""
    pem_inline = os.environ.get("DECOY_RELEASE_KEY_PEM")
    key_file = os.environ.get("DECOY_RELEASE_KEY_FILE")
    if pem_inline:
        data = pem_inline.encode("utf-8")
    elif key_file:
        data = Path(key_file).read_bytes()
    else:
        raise RuntimeError(
            "no release signing key: set DECOY_RELEASE_KEY_FILE or DECOY_RELEASE_KEY_PEM"
        )
    key = serialization.load_pem_private_key(data, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("release key is not an Ed25519 private key")
    return key


def public_key_pem(key: Ed25519PrivateKey) -> str:
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")


def published_public_key_pem() -> str:
    """The committed public key the installer pins. Build tooling asserts the loaded
    private key matches this before signing, so a release can never be signed with a key
    the installer will not trust."""
    return _PUBLIC_KEY_FILE.read_text(encoding="utf-8")


def sign_bytes(data: bytes, key: Ed25519PrivateKey) -> str:
    """Return a base64 detached Ed25519 signature over exactly ``data``."""
    return base64.b64encode(key.sign(data)).decode("ascii")


def sign_file(path: str | Path, key: Ed25519PrivateKey) -> Path:
    """Write ``<path>.sig`` holding the base64 detached signature over the file's bytes.
    Returns the signature path."""
    path = Path(path)
    sig = sign_bytes(path.read_bytes(), key)
    sig_path = path.with_name(path.name + ".sig")
    sig_path.write_text(sig + "\n", encoding="utf-8")
    return sig_path


def _cmd_keygen(args: argparse.Namespace) -> int:
    """Dev/bootstrap helper: generate a release keypair. Writes the private key 0600 and
    prints the public key (to commit as release-key.pub.pem). The real launch key is
    generated once in the secret store, not here."""
    key = Ed25519PrivateKey.generate()
    priv_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    out = Path(args.out)
    fd = os.open(str(out), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(priv_pem)
    pub = public_key_pem(key)
    if args.pub:
        Path(args.pub).write_text(pub, encoding="utf-8")
    sys.stderr.write(f"wrote private key (0600) to {out}\n")
    sys.stdout.write(pub)
    return 0


def _cmd_sign(args: argparse.Namespace) -> int:
    key = load_private_key()
    if args.assert_published:
        from decoy.distribution.signing import _raw_public_bytes_from_pem

        if _raw_public_bytes_from_pem(public_key_pem(key)) != _raw_public_bytes_from_pem(
            published_public_key_pem()
        ):
            sys.stderr.write("refusing to sign: loaded key != committed release-key.pub.pem\n")
            return 2
    for f in args.files:
        sig_path = sign_file(f, key)
        sys.stderr.write(f"signed {f} -> {sig_path}\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="sign_release")
    sub = ap.add_subparsers(dest="cmd", required=True)
    kg = sub.add_parser("keygen", help="generate a release keypair")
    kg.add_argument("--out", required=True, help="private key output path (written 0600)")
    kg.add_argument("--pub", help="also write the public key PEM here")
    kg.set_defaults(func=_cmd_keygen)
    sg = sub.add_parser("sign", help="detached-sign one or more files")
    sg.add_argument("files", nargs="+")
    sg.add_argument(
        "--assert-published",
        action="store_true",
        help="refuse unless the loaded key matches the committed public key",
    )
    sg.set_defaults(func=_cmd_sign)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
