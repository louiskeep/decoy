"""Build-host release tooling for the Decoy CLI self-hosted distribution.

NOT shipped in the `decoy-cli` wheel: this package runs only on the release build
host / CI. It assembles per-target bundles, signs them and the version document, and
emits the checksums the installer verifies. The private signing key lives only here
(sourced from the environment, never committed); the shipped CLI carries only the
verify side in `decoy.distribution`.

Layout:
  sign_release.py          Ed25519 key custody + detached signing (private-key side)
  build_bundle.py          deterministic per-target bundle assembler
  make_version_document.py  assemble + sign the hosted version document
  install/                 install.sh, install.ps1, uninstall.sh (the distributed scripts)
"""
