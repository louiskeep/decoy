# Decoy CLI: packaging, install, and upgrade

This is the self-hosted distribution for the Decoy CLI (B-2, §CLI-LAUNCH). Decoy
ships the CLI as a signed, versioned, per-platform **bundle** (a standalone
CPython plus the matched engine, native companion, and CLI wheels), served from
Decoy, not from public PyPI. An operator installs and upgrades with one command,
the native companion is on by default, and a missing companion is a loud refusal,
never a silent slow path.

> Status: build lane (RW-B). The real download host, the real version endpoint,
> and the real signing key are not stood up here: this tree is the tooling, the
> contract, and a local test key with a documented plug-in point. The launch
> engine pin is one variable the orchestrator swaps when D-4 lands
> (`packaging/pin.env`).

## For an operator: install, verify, upgrade

### Install

```sh
curl -LsSf https://decoy.dev/install.sh | sh
# or, offline / air-gapped: download the bundle + SHA256SUMS + SHA256SUMS.sig,
# then:  DECOY_INSTALL_LOCAL_DIR=/path/to/download  sh install.sh --version X.Y.Z
```

The installer verifies a SHA-256 checksum and a signature **before** it extracts
anything, lays the runtime down under `~/.decoy/versions/<version>/`, points
`~/.decoy/current` at it, and puts a `decoy` launcher on your PATH
(`~/.local/bin/decoy`). A bad checksum or signature is a hard stop: nothing is
installed. Pin a version with `--version X.Y.Z`; remove everything with
`install.sh uninstall`.

Supported targets: `linux-x86_64`, `linux-aarch64`, `macos-arm64`,
`windows-x86_64` (use `install.ps1` on Windows). A host that maps to no bundle
fails loudly rather than installing a partial or slow runtime. (macOS Intel is an
open target decision; see "Open decisions" in the distribution spec.)

### Upgrade

```sh
decoy upgrade          # install the latest matched runtime (verify, then swap)
decoy upgrade --check  # just report whether a newer version exists
```

`decoy upgrade` reads the Decoy-hosted version document, picks the bundle for your
platform, and re-runs the installer against it: the same verify-before-extract,
then an atomic `current`-symlink swap (rollback is the swap back). An interactive
session also prints a one-line "new version available" notice at startup;
suppress it with `--no-update-check`, the `DECOY_NO_UPDATE_CHECK` env var, no TTY,
CI, or `--json` / `--quiet`. The check fetches only a version string: no data, no
identifiers, no telemetry.

### Recorded flow (the R1 canonical smoke target)

A real end-to-end run of assemble, sign, install, refuse-on-tamper, and
check-for-update (temp paths shown as `~/` for readability):

```text
## 1. install (verify checksum + signature, then extract)
decoy-install: target: linux-x86_64
decoy-install: version: 0.1.0
decoy-install: signature OK
decoy-install: checksum OK
decoy-install: installed decoy 0.1.0 for linux-x86_64.
decoy-install: launcher: ~/.local/bin/decoy
installed tree:  bin  bundle-manifest.json  python  venv  wheels

## 2. a tampered bundle is refused (nothing installed)
decoy-install: target: linux-x86_64
decoy-install: version: 0.1.0
decoy-install: signature OK
decoy-install: CHECKSUM MISMATCH for decoy-0.1.0-linux-x86_64.tar.gz (...). Refusing to install.
(exit 1) refused, as expected
confirmed: no runtime was laid down

## 3. upgrade --check against the version document
current 0.0.1 -> update available: True  latest 0.1.0
```

Reproduce it locally end to end with a stub host:

```sh
packaging/sign/gen-test-key.sh /tmp/keys
# ... assemble + sign a bundle set into a channel dir (see "Build steps") ...
python packaging/version/serve_stub.py /tmp/channel --port 8000 &
DECOY_INSTALL_BASE_URL=http://127.0.0.1:8000 \
DECOY_INSTALL_PUBKEY=/tmp/keys/decoy-release.pub \
  sh packaging/install/install.sh --version 0.1.0
```

## For the release pipeline: per-platform build steps

Each per-target bundle is assembled from inputs the engine's already-green native
matrix and python-build-standalone provide; this tooling does the assembly,
signing, and the version document. The native wheel matrix is NOT rebuilt here
(`decoy-engine/.github/workflows/native-companion.yml` builds it; see
`decoy-engine/docs/native/supported-matrix.md`).

1. **Pins.** `packaging/pin.env` holds the one launch engine version, the native
   ABI tag, the standalone CPython version, and the CLI version. The orchestrator
   swaps `DECOY_LAUNCH_ENGINE_VERSION` when D-4 cuts the launch engine; everything
   below repins off that one value.
2. **Wheels.** Obtain the matched `decoy-engine`, `decoy-engine-native` (the
   target's wheel), and `decoy-cli` wheels at the pinned versions. The assembler
   asserts engine and native are the SAME version and match the pin, the native
   wheel is built for the target's architecture, and the CLI matches its pin;
   a mismatch fails the build (`BundleSpecError`).
3. **Standalone CPython.** Fetch the python-build-standalone distribution for the
   target's triple (`packaging/bundle/targets.py`), pinned to
   `DECOY_LAUNCH_PYTHON_VERSION` / `DECOY_LAUNCH_PYTHON_BUILD`.
4. **Assemble** (on the matching host):

   ```sh
   python -c "from bundle.assemble import BundleSpec, assemble; \
     assemble(BundleSpec.build(target_key='linux-x86_64', cpython_src='<cpython>', \
       wheel_paths=[...], output_root='build'))"
   # (run with packaging/ on PYTHONPATH)
   ```

   This installs the matched wheels into a private venv under the embedded
   CPython, writes the launcher (which sets `DECOY_MANAGED_RUNTIME=1`), and writes
   `bundle-manifest.json`.
5. **Smoke** each bundle on its target: `decoy doctor`, a real mask run, and an
   assertion that the native route actually engaged (not a silent Python
   fallback). The manifest records the expected native ABI for this check.
6. **Package + sign.** Tar each bundle to `decoy-<version>-<target>.tar.gz`, then
   `packaging/sign/sign.sh <artifact-dir> <private-key>` writes `SHA256SUMS` and
   `SHA256SUMS.sig`.
7. **Publish** the bundles, `SHA256SUMS`, `SHA256SUMS.sig`, `install.sh` /
   `install.ps1`, and the updated `version.json` to the download host.

## The version document contract

`GET https://decoy.dev/cli/version.json` returns the document in
`packaging/version/version.schema.json` (example: `version.example.json`). It
carries `latest`, `min_supported`, `yanked`, `message`, and a per-target
`artifacts` map, plus a `schema_version`. Every field is optional with a defined
default, so an older CLI reading a newer document degrades cleanly. The client is
`decoy._version_endpoint`; the stub server is `packaging/version/serve_stub.py`.

## Signing key: the handoff point

See `packaging/sign/README.md` for the full scheme, custody, and rotation. In
short: the real signing key is generated and held out of band (never in this
repo); at release, point `sign.sh` at the real key and replace the committed
public TEST key in three places (`packaging/install/decoy-release.pub` and the
embedded key block in `install.sh` and `install.ps1`) with the real public half.
