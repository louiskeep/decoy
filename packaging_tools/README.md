# `packaging_tools` -- Decoy CLI release pipeline (build host only)

This package is **not shipped** in the `decoy-cli` wheel. It runs on the release build
host / CI to assemble, sign, and publish the self-hosted CLI distribution. The shipped CLI
carries only the verify side, in `decoy.distribution`.

> Named `packaging_tools` (not `packaging`) on purpose: `packaging` is the PyPI library
> `decoy.distribution.version_document` imports for PEP 440 ordering, and a repo-root
> `packaging/` package would shadow it.

## Layout

| Path                       | Role                                                             |
| -------------------------- | ---------------------------------------------------------------- |
| `sign_release.py`          | Ed25519 key custody + detached signing (the only private-key code) |
| `build_bundle.py`          | deterministic per-target bundle assembler                        |
| `make_version_document.py` | assemble + sign the hosted version document                      |
| `install/install.sh`       | POSIX installer (shipped to users)                               |
| `install/install.ps1`      | Windows installer (shipped to users)                             |
| `install/uninstall.sh`     | POSIX uninstaller                                                 |
| `smoke_install.py`         | end-to-end acceptance smoke                                       |

## Signing + key custody

Established methodology: Ed25519 via `cryptography`, the same scheme and raw-signature
bytes as the platform's output-passport / air-gapped-manifest signer
(`decoy-platform/api/crypto/signed_envelope.py`). No hand-rolled crypto, no second signer.
The detached signature is over the exact on-disk file bytes, so three verifiers agree:
`openssl pkeyutl -verify -rawin` (install.sh), `decoy.distribution.signing.verify_detached`
(`decoy upgrade`), and the platform primitive (audit).

- The **private key** is sourced from the environment and **never committed**:
  `DECOY_RELEASE_KEY_FILE` (a PEM/PKCS8 0600 file in the release secret store) or
  `DECOY_RELEASE_KEY_PEM` (inline, for a CI secret). It is read only in `sign_release.py`.
- The **public key** is published at `src/decoy/distribution/release_key.pub.pem` (shipped
  in the wheel, pinned by `decoy upgrade`) and embedded into `install.sh` / `install.ps1`
  at publish time (the `__DECOY_RELEASE_PUBLIC_KEY__` placeholder). The committed file is a
  placeholder; a build that still carries it refuses to upgrade rather than trust an
  unfilled key.
- **Rotation:** generate a new keypair, publish the new public key in a signed release,
  and keep the old public key in a documented trust set for one deprecation window so
  in-flight installers still verify prior releases.

Generate a dev/bootstrap keypair:

```sh
python -m packaging_tools.sign_release keygen --out release-key.pem --pub release_key.pub.pem
```

## Build pipeline

The native wheel matrix is already green and durable-signed by the engine repo's
`native-companion-release.yml` (tag-triggered). Consume those wheels; do not rebuild them.

1. Populate a wheels dir with the three matched wheels (`decoy-cli`, `decoy-engine`,
   `decoy-engine-native` for the target) **and their full dependency closure**:

   ```sh
   pip download --dest wheels --find-links <signed-wheels> \
       decoy-cli==<ver> decoy-engine decoy-engine-native
   ```

2. Fetch the pinned standalone CPython for the target (python-build-standalone; `uv python
   install <ver>` fetches exactly this).

3. Assemble + sign each per-target bundle:

   ```sh
   DECOY_RELEASE_KEY_FILE=release-key.pem \
   python -m packaging_tools.build_bundle \
       --version <ver> --target linux-x86_64 \
       --python <standalone-cpython-dir> --wheels wheels --out dist --sign
   ```

   Produces `dist/decoy-<ver>-<target>.tar.gz` + `.sha256` + `.sig`. The archive is
   reproducible (sorted entries, fixed mtime/uid/gid, normalized shebangs, no bytecode).

4. Assemble + sign the version document:

   ```sh
   DECOY_RELEASE_KEY_FILE=release-key.pem \
   python -m packaging_tools.make_version_document \
       --version <ver> --min-supported <floor> \
       --dist dist --base-url https://decoy.dev/cli/<ver> \
       --out version.json --sign
   ```

5. Publish the bundles, their sidecars, and `version.json`(`.sig`) to the download host.

## Acceptance smoke

```sh
python -m packaging_tools.smoke_install \
    --python <standalone-cpython-dir> --wheels <wheels-with-closure> --work /tmp/decoy-smoke
```

Builds a real signed bundle, serves it locally (bound to 0.0.0.0, LAN-only), and asserts:
clean install + `decoy --version` + `decoy run`; checksum refusal on a tampered byte;
signature refusal on a corrupted signature; a loud native self-check refusal when the
companion is removed; and a real `decoy upgrade` 0.1.0 -> 0.2.0. The
rollback-on-injected-failure path is asserted by the installer unit test.

## Open lane decisions (flag to Cam)

- **Windows signature tooling.** install.ps1 verifies Ed25519 via `openssl` on PATH
  (Git-for-Windows ships it) and refuses if absent. A bundled/pinned `minisign` is the
  alternative if requiring openssl is friction.
- **macOS Intel (x86_64):** unsupported at launch. Rosetta-on-arm64 or adding the target
  grows the matrix.
- **Download host + signing-key custody store:** static site + CDN vs object storage;
  where the private key lives and its rotation cadence.
