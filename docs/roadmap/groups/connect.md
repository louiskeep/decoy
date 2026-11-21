# Sources and targets

Status: current

Part of the roadmap: [ROADMAP.md](../../ROADMAP.md). Path shorthand (`E:`, `C:`, `P:`, vault) is defined there.

Rows keep their number from the pre-split track. A row number or section number that is not in a group file is a closed row or old section in the [snapshot](../../archive/2026-11-18-roadmap-before-split.md).

## 1.0

Blocks the 1.0 release.

None.

## Later (1.x)

Additive. Not scheduled until a 1.x release picks it up.

| # | Item | Repo | State | Branch, plan or handoff | After |
|---|---|---|---|---|---|
| 64 | CLI-CLOUD: S3 and GCS in the CLI through the DELIV cloud run prefix and conditional pointer | CLI | IN PROGRESS; owner 2026-11-06: CLI V1 (UX map Q6 closed). Plan `E:plan/cli-cloud` (`2026-11-12-cli-cloud.md`), 12 slices (EC0 to EC5, REL-C, CC1 to CC5). EC0 MERGED (engine #540, `a6308f2b`, 2026-11-12): S3 and GCS target tables in the delivery plan. EC1 MERGED (engine #542, `c0961a17`, 2026-11-12): one S3 client and classified connector errors. EC2a MERGED (engine #549, `13778a0d`, 2026-11-12): one S3 put path and SDK floors. EC1 and EC2a are in engine 0.23.0, which the CLI now pins (CLI #233). Owner 2026-11-12: one real S3 and one real GCS bucket run approved. Plan revision 3.5 (`bfbcefd6`, 2026-11-13) aligns cloud vaults and evidence with B-6 and DELIV 3.5; plan gate green (Dennis round 1, then a Codex fix pass). Owner Q-H answered (a): after an unknown pointer result, follow DELIV W6 | `E:plan/cli-cloud` `bfbcefd6` | CLI delivery |
| 64b | CLI-DB-SRC: PostgreSQL as a pipeline source (`type: postgres` with a value-free connection reference, a table list and the CONFIG-EXPLICIT column rules) through the engine `postgres_snapshot` primitive; needs a Postgres CI lane (CI-P2 markers, unparked for the engine and CLI) | engine, CLI | NOT STARTED; owner 2026-11-06: CLI V1 | CONFIG-EXPLICIT, CLI-IO | CLI delivery |
| 82 | F07: bounded path-observation discovery, nested-path relations, JSONB coverage | engine | PARTLY MERGED. Plan `E:plan/f07-path-discovery` (revision 3). 82-E1a MERGED (engine #636, `2d01b91af`, 2026-11-17): the nested handler moved to `nested/_handler.py`, no handler line changed. 82-E1, 82-E2a (scan-set core models move to `profiling/_scan_core.py`) and 82-E3a (the nested child is read through one function, `_nested_json`) MERGED, all behavior-preserving and in engine 0.28.0. 82-E3b (several rules per nested column) is built and reviewed (Codex round 3, no V1 findings) as engine draft PR #684, held until 1.1 under the build-ahead rule. Left: E2b, E3b merge, E4a, E4b, E5 | `E:plan/f07-path-discovery` | NAME-REMOVAL |
| 86 | F01: PostgreSQL application-ready write target (staging, constraint, index and sequence restore, atomic publish) and the type-mapping report | engine, CLI | NOT STARTED; owner 2026-11-06: CLI V1 | none | Phase 2 rows; F22 |
| 87 | F02: SFTP, cloud scan, subset against cloud; retry executor; content digest on `WriteResult` | engine, CLI | PARTLY MERGED. Plan written 2026-11-17 (revision 3, Dennis round 2 applied): `E:plan/f02-sftp-cloud`, six engine slices E1 to E6, then the release and four CLI slices C1 to C4. E1 MERGED (one retry executor and S3 body resume) and E6 MERGED (remote subset sources through local copies), both in engine 0.28.0. Left: E2 to E5, the release and C1 to C4 | `E:plan/f02-sftp-cloud` | CLI-CLOUD; F22 adapter |

### Candidates with no plan yet

Non-breaking ideas, so v1+ by rule. A candidate becomes a row in the table above when a release picks it up.

| Item | Source | Why it does not break |
|---|---|---|
| F03 file unions (several files as one logical table) | Council features | New optional source key; single-file configs unchanged. |
| F05 fixed-width streaming | Council features | Turns a refusal on large fixed-width files into a success. |
| F42 Unix streams | Council features | New input and output form. |
| F49 clone-system handoff | Council features | New handoff after a valid published output. |
| X-01 Avro and ORC files | Expansion candidates X-01 to X-25 | New formats. |
| X-02 JSON and JSONL with nested path masking | Expansion candidates X-01 to X-25 | New format and path syntax. |
| X-03 Excel workbooks | Expansion candidates X-01 to X-25 | New format. |
| X-04 XML with path masking | Expansion candidates X-01 to X-25 | New format. |
| X-05 Delta Lake and Apache Iceberg tables | Expansion candidates X-01 to X-25 | New formats. |
| X-06 More databases (MySQL, SQL Server, Snowflake, BigQuery; MongoDB later) | Expansion candidates X-01 to X-25 | New connectors. |
| X-20 Document redaction (PDF, DOCX, email) | Expansion candidates X-01 to X-25 | New formats and extras. |
| X-21 DICOM medical imaging de-identification | Expansion candidates X-01 to X-25 | New format and extra. |
| X-22 Text in images and scans (OCR redaction) | Expansion candidates X-01 to X-25 | New extra. Model based, so it states a weaker guarantee of its own. |
| X-23 Faces and licence plates in images and video | Expansion candidates X-01 to X-25 | Same. |
| X-24 Audio redaction | Expansion candidates X-01 to X-25 | Same. |
| 11 New input formats and databases (same as X-01, X-06) | DuckDB opportunities (vault `v2/duckdb/`, platform `plan/v2-duckdb-plans`) | See those. |
| 12 Writing masked output back into a database | DuckDB opportunities (vault `v2/duckdb/`, platform `plan/v2-duckdb-plans`) | New write target. |
| 13 SQL filters on sources | DuckDB opportunities (vault `v2/duckdb/`, platform `plan/v2-duckdb-plans`) | New optional source key. |
| SFTP host-key fingerprint pinning | findings-register, after V1 | New option. Pinning by default would refuse connections that work today. |

## Maintenance

No user-visible change. Merges at any time and never gates a release.

None.
