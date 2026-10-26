"""Distribution + update machinery shared by the shipped CLI and the build host.

This subpackage holds the pure, dependency-light primitives that both the release
build tooling (`packaging_tools/`, build host only) and the installed CLI (`decoy
upgrade`, the startup version notice) need: Ed25519 signature verification, the
bundle checksum manifest, the version-document contract, and the on-disk layout of
the managed runtime. Keeping one copy here is what lets the installer, `decoy
upgrade`, and the build host verify the *identical* signed bytes.

Signing (the private-key side) deliberately lives on the build host only
(`packaging_tools/sign_release.py`); nothing here needs a private key, so none is ever
imported into the shipped wheel.
"""
