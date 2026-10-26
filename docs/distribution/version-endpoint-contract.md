# Version endpoint contract (`cli-version-document/v1`)

The Decoy-hosted version document is the source of truth for the self-hosted update
channel. It feeds `install.sh` / `install.ps1`, `decoy upgrade`, and the startup update
notice. For V1 it is a **static file** served behind a CDN; nothing requires a live
service.

Treat it as an external, versioned contract (per the api-and-compatibility rule): the
schema is versioned, and an older CLI reading a newer document degrades cleanly rather
than crashing.

## Location

```
https://decoy.dev/cli/version.json        the signed document (canonical JSON)
https://decoy.dev/cli/version.json.sig    detached Ed25519 signature (base64) over the file bytes
```

Per-version bundles live under the same base:

```
https://decoy.dev/cli/<version>/decoy-<version>-<target>.tar.gz
https://decoy.dev/cli/<version>/decoy-<version>-<target>.tar.gz.sha256
https://decoy.dev/cli/<version>/decoy-<version>-<target>.tar.gz.sig
```

## Document shape

The file bytes are **canonical JSON**: `json.dumps(payload, sort_keys=True,
ensure_ascii=False, separators=(",", ":"))`. The signer signs exactly those bytes, so the
shell installer (`openssl pkeyutl -verify -rawin`) and `decoy upgrade`
(`decoy.distribution.signing.verify_detached`) verify the identical signature with no
re-serialization step.

```json
{
  "schema_version": "cli-version-document/v1",
  "latest": "0.1.0",
  "min_supported": "0.1.0",
  "yanked": ["0.0.9"],
  "message": "",
  "generated": "2026-10-26T00:00:00Z",
  "artifacts": {
    "linux-x86_64":  {"url": "...", "sha256": "<hex>", "sig": "<url>"},
    "linux-aarch64": {"url": "...", "sha256": "<hex>", "sig": "<url>"},
    "macos-arm64":   {"url": "...", "sha256": "<hex>", "sig": "<url>"},
    "windows-x86_64":{"url": "...", "sha256": "<hex>", "sig": "<url>"}
  }
}
```

| Field           | Meaning                                                                 |
| --------------- | ----------------------------------------------------------------------- |
| `schema_version`| Contract version. A consumer that does not recognize it refuses to act. |
| `latest`        | Newest non-yanked release. The default install/upgrade target.          |
| `min_supported` | Floor below which a CLI should hard-upgrade (advisory in V1).           |
| `yanked`        | Versions pulled post-release; never offered as an upgrade.              |
| `message`       | Optional advisory shown on upgrade / notice.                            |
| `generated`     | UTC timestamp the document was produced.                                |
| `artifacts`     | One `{url, sha256, sig}` per supported target.                          |

Version ordering is PEP 440 (`packaging.version`).

## Compatibility rules

- **Unknown top-level fields are ignored** by the client (forward-compatible).
- A **missing target** in `artifacts` is not an error: that target simply has no bundle in
  this document, and the client refuses that one target rather than crashing.
- The client **never** trusts the document before verifying its signature against the
  pinned release key. The document carries the per-bundle `sha256`, so the installer
  verifies the checksum against a signed source, and the bundle's own `.sig` is the
  trust anchor.
- The startup notice reads only `latest`; it sends no data and fails silent.

## Rollback

The release unit is one signed bundle set plus the updated version document. To roll a
release back, re-point `latest` at the previous version and re-sign the document;
`decoy upgrade` and a fresh install then resolve the previous bundle. The managed runtime
keeps the prior version on disk, so a client rolls back with `decoy upgrade --version
<previous>` without any network change.
