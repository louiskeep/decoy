# Parity C2: cloud and database I/O in the CLI

Status: plan, PRE-RELEASE (2026-10-24). Part of the parity program; source: parity audit §4 rows "S3 / GCS",
"SFTP", "Postgres snapshot input", §7 ("currently platform-only, but engine work"), §9 row 1. Overlaps
roadmap B-1 (DuckDB-in CLI source) and depends on engine E2b for the shared reader.

Rules consulted: 00-universal, development-loop, risk-and-exceptions, security, config-secrets-and-supply-
chain, api-and-compatibility, reuse-first, observability-and-resilience, testing, documentation; CLI
`CLAUDE.md`.

Risk: R2 (credentials handled by a new consumer; network I/O failure paths; a public claim on the website
depends on it).

## 1. Guarantee and non-goals

Guarantee: a pipeline whose `sources`/`targets` declare `type: s3` or `type: gcs` runs through `decoy run`
and `decoy.mask()` using the engine's own connectors, with credentials resolved from the environment, a
file, or the cloud SDK's default chain, never from the YAML; a Postgres snapshot source reads through the
engine's DuckDB primitive. Output on a cloud target is published all-or-nothing per table (upload after a
successful local write, then verify size), and a failed upload is a runtime error, not a success.

Non-goals: a credential store (platform), SFTP as a run source/target (not a config source type in the
engine; follow-on when `SourceDescriptor` gains it), multipart/spool tuning beyond the SDK defaults,
database write-back (V2 Tier 2), warehouse readers (B-6).

## 2. What exists

- Engine: `S3Source`/`GCSSource` descriptors with opaque `credentials_ref` (`config/_sources.py:216-275`);
  `connectors/s3.py::S3FileSource`/`S3FileSink`, GCS and SFTP equivalents over the `sdk.py` ABCs;
  `connectors/postgres_snapshot.py` (platform-wired only); after E2b, `read_source_table(descriptor,
  base_dir, *, open=...)`.
- CLI: `cli/extras.py::check_cloud_endpoints_supported` refuses cloud endpoints before any I/O;
  `check_cloud_endpoints` probes the SDK; `[cloud]` extra installs boto3 and google-cloud-storage;
  `_load_sources_from_config`, `_write_mask_outputs`, `_run_chunked_mask` are the three local I/O helpers.
- Platform: `api/cloud/io.py::_resolve_credentials_ref` and the S5 credential-safety patterns (delete
  creds before raising SDK calls, `raise ... from None`, type-name-only error details).

## 3. Established solutions

- Credentials: do not invent storage. `credentials_ref` in the CLI resolves as `env:NAME` (JSON or
  `KEY=VALUE` pairs), `file:/path` (0600-checked), or absent, in which case boto3's default credential
  chain and GCS Application Default Credentials apply. This mirrors `mask_secret_ref`'s `env:`/`file:` the CLI
  already ships and the SDKs' documented resolution order.
- Upload-after-local-write with size verification is the platform's H2 pattern and S3's recommended
  idempotent single-object PUT for objects under the multipart threshold.
- Error hygiene: adopt the platform's five S5 patterns verbatim; the CLI's existing leak sentries extend to
  credential strings.

## 4. Design

- New `cli/_cloud_io.py` (under 600 LOC): `open_source(descriptor) -> binary stream` and
  `publish_target(descriptor, local_path)`, built on the engine `FileSource`/`FileSink` connectors;
  credential resolution in one function with the S5 patterns.
- `_load_sources_from_config` calls engine `read_source_table` with `open=open_source`; `_write_mask_outputs`
  writes locally to a temp file in the target's spool dir (`--spool-dir`, default user cache) then
  `publish_target`. `_run_chunked_mask` (until C3) streams chunks to the same temp file.
- Postgres: `type: postgres_snapshot` source (engine descriptor exists platform-side only; add it to
  `SourceDescriptor` in the engine as a small additive change, tracked as an engine slice in this plan) with
  `dsn_ref: env:NAME`; the CLI calls the engine snapshot primitive to a temp Parquet then proceeds as a
  file source.
- `validate preflight` reports cloud endpoints as "remote: not sized" rather than skipping silently.
- Delete `UnsupportedCloudEndpointError` and its tests (pre-GA hard delete) once both sources and targets
  are wired; keep `check_cloud_endpoints` (SDK probe).

## 5. Slices and acceptance

1. **C2a credentials + S3/GCS sources** against moto/`fake-gcs-server` fixtures (no live cloud in CI):
   same bytes as a local run of the downloaded file; missing creds fail closed with a coded usage error;
   sentry proves no credential string in stdout/stderr/JSON/notify payloads on any failure.
2. **C2b S3/GCS targets** with publish-after-write and size verify; a forced upload failure exits
   `EXIT_RUNTIME` and leaves the local spool file with a message naming it.
3. **C2c Postgres snapshot source** (engine descriptor + CLI wiring) against a dockerised Postgres fixture.
4. **C2d docs**: README cloud section, `explain connectors`, website `cli.njk` and public connector docs
   lose the "Platform feature" carve-out (web change tracked in P3).

## 6. Failure modes

Partial upload (size verify + runtime error); credentials in tracebacks (S5 patterns + sentry); clock skew
and retries (SDK defaults; bounded, no custom retry loop); large objects on small disks (`--spool-dir`
and a free-space check before download, reusing the engine's disk-budget helper from out-of-core).

## 7. Done when

All four slices merged; the website claim "nothing is held back" is true for connectors; C3 can route the
same opener through the dispatcher.
