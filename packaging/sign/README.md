# Signing the Decoy CLI distribution

## Scheme

Each release publishes, per version:

- one per-target bundle tarball, `decoy-<version>-<target>.tar.gz`,
- a `SHA256SUMS` manifest listing every artifact's SHA-256,
- `SHA256SUMS.sig`, a detached signature over the manifest.

The manifest is signed once; each artifact is checksummed. A client verifies the
manifest signature, then verifies each artifact against the manifest. This is the
rustup / uv pattern (sign the manifest, checksum the artifacts), not custom
crypto.

**Signature primitive: ECDSA P-256 (prime256v1) with SHA-256, via `openssl
dgst`.** It is chosen so the bootstrap installer can verify with the `openssl`
already on the box: `openssl dgst -sha256 -verify` works on both OpenSSL (Linux,
Windows git) and LibreSSL (macOS) command lines, with no extra binary to install
first. The distribution spec leaves the signing TOOL an open lane decision
(minisign vs cosign vs a hosted signing service); whichever is chosen only has to
emit a detached signature this primitive verifies, or the installer's verify step
swaps to that tool's verifier. The format is the contract, not the tool.

## Local build + test

```sh
# 1. Generate a LOCAL TEST keypair (private stays out of git).
packaging/sign/gen-test-key.sh /tmp/decoy-keys

# 2. Sign a directory of built bundle tarballs.
packaging/sign/sign.sh /path/to/artifacts /tmp/decoy-keys/decoy-release-test.key

# 3. The installer verifies with the matching public key.
DECOY_INSTALL_PUBKEY=/tmp/decoy-keys/decoy-release.pub \
DECOY_INSTALL_LOCAL_DIR=/path/to/artifacts \
  packaging/install/install.sh --version <version>
```

The committed `packaging/install/decoy-release.pub` and the key embedded in
`install.sh` / `install.ps1` are the TEST key's public half, so the shipped
installer verifies test bundles out of the box in CI. They are placeholders.

## The real signing key: custody, rotation, and the plug-in point

> This is the handoff point. The real key is NOT in this repo and is never
> produced by it.

- **Generation + custody.** The real release key is generated out of band and
  held in the release secret store (the same custody system the platform's
  master key uses, per `config-secrets-and-supply-chain`), never on a developer
  laptop and never committed. Only the release pipeline reads the private half,
  from the secret store at sign time; the private key never lands in a repo, an
  artifact, or a log.
- **Plug-in point (two edits at release).**
  1. `sign.sh` already takes the private key as a path argument: point it at the
     key material the pipeline mounts from the secret store. No code change.
  2. Replace the committed public key in three places with the real public half:
     `packaging/install/decoy-release.pub`, the `EMBEDDED_PUBKEY` block in
     `packaging/install/install.sh`, and the `$EmbeddedPubKey` block in
     `packaging/install/install.ps1`. (The embedded copies are what a `curl | sh`
     bootstrap trusts with no prior download.)
- **Rotation.** Keep the public key behind a versioned filename on the download
  host and in the installer; a rotation ships a new installer carrying the new
  public key and re-signs the live bundles with the new private key. Because the
  version document points at `latest` and the `current` symlink is swappable, a
  rotation is a re-sign + re-publish, not a data migration. Document the old key
  as retired; do not delete it until no published bundle is signed by it.

## Why not commit any key

A committed private key is a disclosed secret, the moment it lands in history.
`.gitignore` in `packaging/` excludes `*.key` and the test-key directory; the
signing scripts take the private key as an argument so there is never a reason to
place one in the tree.
