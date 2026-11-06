# V2 and V3 expansion candidates: new data, new masks, new generators

Status: proposal (for the V2/V3 planning discussion; nothing here is scheduled)

Part of the roadmap: [ROADMAP.md](../ROADMAP.md). Path shorthand (`E:`, `C:`, `P:`, vault) is defined there.
Indexed from the V2 backlog in [out-of-scope.md](out-of-scope.md).

This document proposes features that widen Decoy's core: more kinds of input and output, more mask
and privacy techniques, more generators, documents, and media (images, video, audio). Each entry
gives what it is, how we would build it, who uses it and why, its difficulty, and a recommended
placement. Where an entry overlaps a Council-V2 feature (F-number) or an existing roadmap row, it
says so; the entry then adds detail to that item rather than starting a second one.

## How to read this

**Placement**

| Tag | Meaning |
|---|---|
| V1+ | Small, self-contained; fits a point release after CLI V1 without new architecture |
| V2 | Builds on code we already have; needs a plan and some new engine surface |
| V3 | New subsystem, new dependency class (ML models, streaming) or a weaker guarantee model |

**Difficulty**

| Tag | Rough size | Typical shape |
|---|---|---|
| S | 1 to 2 slices | One strategy, provider or reader; tests and docs |
| M | 3 to 5 slices | New config surface, planner and route work, a new extra |
| L | 6 to 10 slices | New subsystem, many routes, new evidence or report types |
| XL | A program | New runtime model, ML dependencies, or long-running services |

## Baseline: what ships today

Read from `E:docs/capability-matrix.md` and the source on 2026-11-06.

- Input formats: CSV, Parquet and fixed width (`E:src/decoy_engine/config/_sources.py`). File
  targets: CSV and Parquet. PostgreSQL snapshot source (`E:src/decoy_engine/connectors/postgres_snapshot.py`).
  Connectors: S3, GCS, SFTP (source and sink).
- 24 mask strategies, 12 generation strategies, 34 synthetic providers (mostly US identifiers).
- Detection: 11 regex detectors fire on the built-in path; 14 more are registered but only fire
  with injected spans. spaCy NER covers person names and places in prose (`ner` extra).
- Privacy measurement: k-anonymity over quasi-identifiers in `decoy scan`
  (`E:src/decoy_engine/profiling/profiler.py`), DCR and attack checks, and DP building blocks in
  `E:src/decoy_engine/quality/`.
- Synthesis: per-column sampling from `distribution-snapshot/v1`; correlated composites (person,
  address, name and email) on the SDV HMA1 shared-latent pattern.
- 10 disguises (compliance presets), all US or EU-generic.

The gaps are mostly in what data Decoy can reach and what shape it can be in, not in the
column-level strategy set.

## Summary

| ID | Feature | Area | Difficulty | Placement | Related |
|---|---|---|---|---|---|
| X-01 | Avro and ORC files | I/O | S | V1+ | none |
| X-02 | JSON and JSONL with nested path masking | I/O | L | V2 | F07, F03 |
| X-03 | Excel workbooks | I/O | M | V2 | none |
| X-04 | XML with path masking | I/O | M | V2 | X-02 |
| X-05 | Delta Lake and Apache Iceberg tables | I/O | M | V2 | F22 |
| X-06 | More databases (MySQL, SQL Server, Snowflake, BigQuery; MongoDB later) | I/O | L each | V2 (MongoDB V3) | F01, row 64b |
| X-07 | Streaming and change-data-capture masking | I/O | XL | V3 | F42 |
| X-08 | International identifiers, generators and region disguises | Mask | M | V1+ (detectors), V2 (disguises) | F47, DETECT-PROFILES |
| X-09 | Secrets detection | Mask | S | V1+ | none |
| X-10 | Meaning-preserving masks | Mask | S each | V1+ | none |
| X-11 | Better free-text detection | Mask | L | V2 | F08, DETECT-PROFILES |
| X-12 | Formal anonymity enforcement | Privacy | L | V2 | F37 |
| X-13 | Time-series and event masking | Mask | M | V2 | none |
| X-14 | Joint-distribution synthesis (Gaussian copula) | Generate | L | V2 | F48, DPS |
| X-15 | Multi-table synthesis | Generate | XL | late V2 | F48, X-14 |
| X-16 | Generate from a schema | Generate | M | V2 | none |
| X-17 | Edge-case test data | Generate | M | V2 | F46 |
| X-18 | Sequential and event data synthesis | Generate | XL | V3 | X-14 |
| X-19 | File metadata scrubbing | Documents | S | V2 | F38 |
| X-20 | Document redaction (PDF, DOCX, email) | Documents | L | V3 (DOCX and email may move to V2) | X-11 |
| X-21 | DICOM medical imaging de-identification | Media | L | V2 | F47 |
| X-22 | Text in images and scans (OCR redaction) | Media | L | V3 | X-20, X-21 |
| X-23 | Faces and licence plates in images and video | Media | XL | V3 | X-22 |
| X-24 | Audio redaction | Media | XL | V3 or later | X-11 |
| X-25 | Plugin SDK as the home for heavy extras | Enabler | M | V2 | F40 |

Recommended V2 core: X-02, X-08, X-12, X-14, X-21, with X-25 first because the media and model
features depend on it.

---

## 1. Inputs and outputs

### X-01 Avro and ORC files

**What.** Read and write Avro and ORC as file sources and targets, beside CSV, Parquet and fixed
width.

**How.** pyarrow already reads ORC (`pyarrow.orc`) and Avro has a mature reader (`fastavro`, or
Polars' Avro reader). Add the two literals to `FileSource.format` and the target format, route both
through the existing Arrow adapter, and keep the schema (Avro logical types, ORC stripes) on write.
Chunked reading uses ORC stripes and Avro blocks as natural chunk boundaries.

**Who and why.** Data engineers on Hadoop, Hive or Kafka-era estates, where Avro is the default
record format and ORC the default Hive table format. Without it they convert to Parquet first,
which loses Avro schema evolution and adds a copy of the raw data.

**Difficulty.** S. The readers exist; the work is format declaration, the CLI-FMT target path
(row 20) and round-trip tests.

**Placement.** V1+. Small, no new architecture, and it rides the CLI-FMT single target module once
that lands.

### X-02 JSON and JSONL with nested path masking

**What.** JSON documents and JSON Lines files as sources and targets, with masking addressed by
path: `$.customer.email`, `$.items[*].card_number`. The same path selector applies to a JSON column
inside a table (Postgres JSONB, a string column holding JSON).

**How.** Follow JSONPath (RFC 9535) for the selector grammar, with a closed subset (child, wildcard,
array index and slice, no filter expressions) so the planner can check it statically. Two
execution modes:

- Flatten: for records with a stable schema, flatten to columns (Arrow struct and list types),
  mask with the existing strategies, and rebuild. This keeps the chunked and FK machinery.
- Walk: for irregular documents, walk each record and apply strategies at matched paths.

Deterministic strategies (hash, FPE, tokenize) keep joins across a JSON field and a table column.
F07 (JSONB coverage and nested-path relations) needs the same selector; build it once in the
engine and use it for both. Schema discovery for `decoy scan` samples paths and records which are
always present, sometimes present or arrays.

**Who and why.** API and backend teams building fixtures from production payloads; event and log
pipelines; anyone with JSONB columns. JSON is the most common format we cannot open today, and
masking it by flattening by hand loses structure.

**Difficulty.** L. The selector, two execution modes, scan support, chunked JSONL, and the
round-trip guarantee (key order, number formatting) all need care.

**Placement.** V2. It is the most-asked-for missing format, and it shares the path work F07
already needs, so it should be planned together with F07.

### X-03 Excel workbooks

**What.** Read one or more sheets from `.xlsx` as tables and write a masked workbook.

**How.** Read with `fastexcel` (Calamine, which Polars uses) and write with `openpyxl`. Each sheet
is a table; config names the sheet and header row. Preserve cell types and number formats where
the strategy keeps the type; strip formulas or recompute them (configurable, default strip, since
a formula can reference unmasked cells). Workbook properties go through X-19.

**Who and why.** Finance, operations and compliance users whose sensitive data lives in
spreadsheets, and consultants who receive client extracts as workbooks. It opens Decoy to
non-engineering users.

**Difficulty.** M. Type inference, merged cells, formulas and multi-sheet output are the hard
parts; reading is easy.

**Placement.** V2. Useful, but the users it brings are better served once the CLI journey is
settled.

### X-04 XML with path masking

**What.** XML files masked by path (XPath subset), including attributes.

**How.** Stream with `lxml.etree.iterparse` so large files stay bounded. Reuse the X-02 selector
model with an XPath 1.0 subset (child, descendant, attribute, position). Keep namespaces and
declaration as read. Defend against XML entity expansion and external entities (`defusedxml`
settings) since inputs are untrusted.

**Who and why.** Healthcare (HL7 CDA, some FHIR exchanges), finance (ISO 20022, FpML), government
and older enterprise integrations, where XML is still the exchange format.

**Difficulty.** M once X-02 exists.

**Placement.** V2, after X-02.

### X-05 Delta Lake and Apache Iceberg tables

**What.** Read a Delta or Iceberg table (a snapshot or version) and write a masked table as a new
table or a new commit.

**How.** `deltalake` (delta-rs) and `pyiceberg` both expose Arrow datasets, so reading fits the
existing Arrow adapter and chunked routes. Write through each library's transactional commit,
which gives atomic publication for free; it must still follow F22's publication contract. Record
the source snapshot or version in evidence so a run is reproducible.

**Who and why.** Data platform teams on Databricks, Spark, Trino, Snowflake external tables or
AWS lakehouses who need a masked copy for analytics or development. A lakehouse is where much
production analytical data now lives.

**Difficulty.** M. Partitioning, schema evolution and cloud credentials are the work.

**Placement.** V2, after F22 and CLI-CLOUD, which it depends on.

### X-06 More databases

**What.** Database sources and application-ready targets beyond Postgres: MySQL and MariaDB, SQL
Server, Snowflake and BigQuery; MongoDB later.

**How.** Make Postgres (row 64b and F01) the reference adapter and pull a database adapter contract
out of it: snapshot-consistent read, type mapping report, staging, constraint, index and sequence
restore, atomic publish. Each new database implements the contract. Use each vendor's bulk paths
(MySQL `LOAD DATA`, SQL Server bulk copy, Snowflake `COPY INTO` via staged Parquet, BigQuery load
jobs) and ADBC drivers where they exist, so data moves as Arrow. MongoDB needs X-02's path masking
and is V3.

**Who and why.** Teams that refresh development, QA and staging databases from production. The
"masked copy of prod" job is the main reason people buy masking tools, and most estates are not
only Postgres.

**Difficulty.** L per database for an application-ready target; M for a read-only source.

**Placement.** V2 for MySQL, SQL Server, Snowflake and BigQuery (order by customer pull). V3 for
MongoDB.

### X-07 Streaming and change-data-capture masking

**What.** Mask records in motion: Kafka topics, and Debezium change events from a database, using
the same keys and strategies as batch so a value masks the same way in both.

**How.** A long-running consumer that reads a topic, masks each record with deterministic
strategies only (hash, FPE, tokenize, deterministic faker; no strategies that need the whole
column such as shuffle or statistical), and produces to an output topic. Debezium's envelope
(`before`, `after`, `op`) is masked on both images. Exactly-once through Kafka transactions.
Schema Registry for Avro and JSON Schema.

**Who and why.** Teams that keep a non-production environment continuously in sync with
production, or that feed analytics from CDC. Few masking tools offer the same key and strategy
in batch and stream, so this sets Decoy apart.

**Difficulty.** XL. It is a service, not a job: offsets, back-pressure, restarts, monitoring, and
a strategy subset whose limits must be checked at plan time.

**Placement.** V3. It needs a runtime model the CLI does not have, and it fits the platform.

---

## 2. Masking and privacy

### X-08 International identifiers, generators and region disguises

**What.** Detectors, checksum-valid generators and FPE-safe formats for non-US identifiers: UK
NINO and NHS number, Canadian SIN, Indian Aadhaar and PAN, Australian TFN and Medicare, EU national
IDs (for example German Steuer-ID, French NIR, Spanish DNI and NIE, Italian codice fiscale),
passport numbers, IBAN by country, and international phone numbers. Region disguises: UK GDPR,
PIPEDA (Canada), LGPD (Brazil), APPI (Japan), DPDP (India).

**How.** Detectors: regex plus the published check algorithm (mod 11, Luhn, Verhoeff, ISO 7064)
in `E:src/decoy_engine/checksums.py`; Presidio's predefined recognizers and `python-stdnum` are the
reference sources for formats and checks. Phone numbers through `phonenumbers` (libphonenumber).
Generators as `decoy_native` providers that pass the checksum. Locale-aware name and address
generation through Faker and Mimesis locales, which the provider layer already supports. Each
disguise cites its statute.

**Who and why.** Any customer outside the US, and US companies with international customers.
Today a UK or EU dataset gets weak detection and US-shaped fake values, which breaks validation in
the systems that consume the masked data.

**Difficulty.** M overall; S per identifier. The disguises need careful legal reading.

**Placement.** V1+ for detectors and generators (small, independent, high value). V2 for region
disguises, alongside DETECT-PROFILES and F47's packs.

### X-09 Secrets detection

**What.** Detect and mask credentials in data: API keys (AWS, GCP, Stripe, GitHub, Slack),
JWTs, private keys, passwords in connection strings, bearer tokens.

**How.** Use the rule sets from gitleaks and Yelp's detect-secrets (provider-specific patterns
plus entropy checks) as detectors, at both column level and inside free text. Default action is
redact. Scan reports a finding as high severity because a live credential in a dev copy is a
security incident, not only a privacy issue.

**Who and why.** Every team that copies production to development. Production tables often hold
webhook secrets, integration tokens and passwords in config or log columns, and a leaked
credential is worse than a leaked email address.

**Difficulty.** S. Pattern sets are established; the work is the detector entries and tests
against false positives.

**Placement.** V1+. High value, low risk, no architecture.

### X-10 Meaning-preserving masks

**What.** Small strategies or options that keep the property a test or analysis depends on:

- Email: keep the domain or the domain class (corporate versus free mail).
- Phone: keep country and area code; fake the rest.
- Names: keep likely gender and cultural origin of the original (pool selection by attribute).
- IP addresses: keep the subnet prefix (CryptoPAn, prefix-preserving, for network data).
- Card numbers: keep BIN or IIN (issuer) and card brand; fake the rest with a valid Luhn digit.
- Free-text lengths: keep the length class so UI layouts still show realistic text.

**How.** Each is an option on an existing strategy or a provider, using established methods:
CryptoPAn (Xu et al. 2002) for prefix-preserving IP anonymization, FPE over the suffix for phone
and card, name-attribute pools from public name datasets.

**Who and why.** QA and product teams, and analysts. Masked data that loses these properties
breaks tests (a routing rule on country code), dashboards (email domain mix) and fraud models
(BIN).

**Difficulty.** S each.

**Placement.** V1+, one at a time as customers ask. Some (email domain, card BIN) may already be
reachable with `derived` or `formula`; a named option is still clearer.

### X-11 Better free-text detection

**What.** Make free-text masking find more than the 11 regex types plus spaCy person and place:
turn on the 14 registered-but-unreachable detectors (dates, MRN, licence numbers, device IDs and
others), add context-aware scoring, and offer an optional zero-shot model.

**How.** Follow Microsoft Presidio's recognizer design: pattern plus context words plus checksum,
each with a score and a threshold. Add GLiNER (Zaratiana et al. 2023) as an optional zero-shot NER
extra so users can name entity types without training. Keep spaCy as the default. Thresholds and
which models run go into DETECT-PROFILES. Determinism rule stays: a pinned model version gives
the same spans.

**Who and why.** Healthcare (clinical notes), support and CRM teams (tickets, chat logs), HR
(reviews). Free text is where masking most often leaks, and F08 (coherent identity binding in
free text) needs good spans to work.

**Difficulty.** L. The model work is easy to start; measuring recall and false positives on a
labelled corpus, and keeping it deterministic, is the bulk.

**Placement.** V2, with DETECT-PROFILES and before F08.

### X-12 Formal anonymity enforcement

**What.** Go from measuring k-anonymity (which `decoy scan` does today) to enforcing it, and add
the stronger models: l-diversity and t-closeness. The user states a target ("k at least 5,
l at least 3 over diagnosis") and Decoy generalizes or suppresses until it holds, then reports the
result.

**How.** The ARX and sdcMicro approaches:

- Generalization hierarchies per quasi-identifier (age bands, ZIP prefixes, date to month or
  year), reusing `bucketize`, `geo_generalize` and `truncate`.
- A search over hierarchy levels for the least-information-loss solution that meets the target
  (ARX's Flash algorithm, or a simpler bottom-up search for V2).
- Microaggregation for numeric quasi-identifiers (MDAV, Domingo-Ferrer and Mateo-Sanz 2002).
- Record suppression with a budget.
- Cite Sweeney 2002 (k-anonymity), Machanavajjhala et al. 2007 (l-diversity), Li et al. 2007
  (t-closeness).

Output: a risk report (prosecutor, journalist and marketer risk as ARX defines them) and an
information-loss measure, attached to evidence. This is F37's post-mask risk, with enforcement
added.

**Who and why.** Teams releasing data outside the company: research data sharing, regulators,
vendors, HIPAA Expert Determination. They need a stated, measured re-identification risk, not
only "we masked the identifiers".

**Difficulty.** L. The search needs the whole table (not streaming), and the report must be
honest about what it proves (`E:docs/what-we-cannot-prove.md`).

**Placement.** V2, as the delivery of F37.

### X-13 Time-series and event masking

**What.** Masks that keep the shape of time data for one entity: shift all of a patient's or
customer's dates by the same per-entity offset (keeping intervals and order), keep day of week or
seasonality, and add noise to numeric series (meter readings, vitals) while keeping trend.

**How.** Per-entity date offset from an HKDF-derived key on the entity ID (the established
pattern in clinical de-identification, for example the i2b2 and OMOP date-shift practice); extend
`date_shift` with an entity key if it does not already offer one. Series noise with an
autocorrelation-preserving method (noise on differences rather than levels).

**Who and why.** Healthcare (encounters, labs), IoT and utilities, fintech (transaction
sequences). Independent per-row date shifting breaks "admission before discharge" and length-of-stay
analysis.

**Difficulty.** M.

**Placement.** V2.

---

## 3. Data generation

### X-14 Joint-distribution synthesis (Gaussian copula)

**What.** Synthetic tables that keep correlations between columns, not only each column's own
distribution. Today `statistical` samples each column on its own, apart from the fixed composite
groups.

**How.** SDV's GaussianCopula pattern (Patki et al. 2016): fit each marginal (existing snapshot),
transform to normal scores, estimate the correlation matrix, sample correlated normals, transform
back. Extend `distribution-snapshot/v1` with the correlation matrix. For DP, add noise to the
correlation matrix (DPS-4 territory; the DPS plan in `E:docs/backlog/dps-dp-synthetic-implementation.md`
already names joint-distribution DP as the next step). Categorical columns through one-hot or
frequency encoding as SDV does. The quality report already measures shape fidelity; add pairwise
correlation fidelity.

**Who and why.** ML and analytics teams who want data they can train or test models on, and
teams with no permission to use production data at all. Per-column synthesis gives realistic
columns but nonsense rows (a 5-year-old with a mortgage).

**Difficulty.** L. The method is standard; categorical handling, the snapshot schema and the
quality report extensions are the work.

**Placement.** V2, as the heart of F48.

### X-15 Multi-table synthesis

**What.** Synthesize a whole relational schema: parent and child tables with realistic numbers of
children per parent and child values that depend on the parent.

**How.** SDV's HMA1 (Patki et al. 2016): model each child table's size and its distribution
conditioned on the parent, recursively. Decoy already understands declared relationships and FK
preservation, and cites HMA1 for composites. Start with one parent and one child level, then
extend.

**Who and why.** Teams that need a complete synthetic database for development or a demo, with
joins that work and realistic fan-out (orders per customer, claims per policy).

**Difficulty.** XL. HMA1 does not scale well to deep or wide schemas; it needs bounded memory
work like the chunked routes.

**Placement.** Late V2, after X-14.

### X-16 Generate from a schema

**What.** Create valid fake data from a schema alone, with no production data: Postgres or MySQL
DDL, a dbt model, JSON Schema or an OpenAPI spec.

**How.** Parse the schema (`sqlglot` for DDL in many dialects; dbt `manifest.json`; JSON Schema
draft 2020-12), map types and constraints (not null, unique, check, enum, FK, length, pattern) to
generation strategies, and emit a starter generate config the user can refine. Name hints already
in `E:src/decoy_engine/detection/name_hints/` pick providers by column name (`email`,
`created_at`). Foreign keys generate in dependency order.

**Who and why.** Teams starting a new service, teams not allowed to touch production at all, and
open-source and demo users. It is a quick first-run experience: point Decoy at a schema, get data.

**Difficulty.** M.

**Placement.** V2. Strong adoption feature for the CLI; it could be pulled earlier as a CLI
growth lever.

### X-17 Edge-case test data

**What.** Generate deliberately awkward values to find bugs: boundary numbers, empty and maximum
length strings, Unicode (combining marks, emoji, right-to-left, zero-width), SQL and HTML special
characters, leap days, time-zone and daylight-saving edges, nulls where allowed, duplicate-like
keys (case and whitespace variants).

**How.** A generator family with a mix setting ("5 percent edge cases"), drawing from published
lists: the Big List of Naughty Strings, the Unicode test files, and boundary-value analysis from
testing practice (ISO/IEC/IEEE 29119-4). Types and constraints from the schema decide which edge
cases are valid. Deterministic by seed so a failing case reproduces.

**Who and why.** QA and test engineers. Realistic data alone rarely finds the bugs that crash on
"O'Brien" or a 4-byte emoji. This fits F46 (QA scenarios).

**Difficulty.** M.

**Placement.** V2, inside F46.

### X-18 Sequential and event data synthesis

**What.** Synthetic event streams per entity: transactions, logs, clickstreams, claims, with
realistic gaps between events and ordering.

**How.** SDV's PAR model (Zhang et al. 2022) or simpler, explainable methods first: per-entity
Markov chains over event types plus fitted inter-arrival time distributions. Pair with X-14 for
the entity-level attributes.

**Who and why.** Fraud, observability and product analytics teams; anyone testing time-based
logic.

**Difficulty.** XL for a learned model; L for the Markov version.

**Placement.** V3.

---

## 4. Documents

### X-19 File metadata scrubbing

**What.** Remove or rewrite hidden metadata: image EXIF (GPS, camera serial, author), PDF document
information and XMP, Office document properties (author, company, last modified by, revision
history, comments).

**How.** `piexif` or Pillow for images, `pikepdf` for PDF, `python-docx` and `openpyxl` for Office
core and app properties. A per-field policy (drop, keep, mask) like F38's metadata preserve and
redact.

**Who and why.** Anyone sharing documents or images outside the company; legal and compliance
teams. Metadata leaks are common and easy to miss.

**Difficulty.** S.

**Placement.** V2, with F38.

### X-20 Document redaction (PDF, DOCX, email)

**What.** Find PII in documents and produce a redacted document that keeps the layout: PDF (text
layer), Word, and email (`.eml`, `.msg`) including headers and attachments.

**How.** Extract text with positions, run the existing span detectors and `text_mask` (X-11 makes
this much better), then write back:

- PDF: true redaction with `pikepdf` or PyMuPDF's redaction annotations applied, so the
  underlying text and glyphs are removed, not covered by a box. Check the output by re-extracting
  text. Scanned PDFs need X-22.
- DOCX: replace runs in `python-docx`, keeping style; handle text split across runs.
- Email: the standard library `email` package for headers and bodies; attachments go back
  through the matching handler.

**Who and why.** Legal discovery, insurance claims, HR, customer support, public records
requests. These users have documents, not tables, and they are a large market.

**Difficulty.** L. Faithful layout and true PDF redaction are the hard parts.

**Placement.** V3 for PDF. DOCX and email are simpler and could move to late V2 if a customer
asks.

---

## 5. Images, video and audio

These features depend on ML models, and their output is not guaranteed to be byte-for-byte
reproducible across hardware. Decoy's determinism guarantees cannot be carried over as they stand.
Ship them as optional extras through the plugin SDK (X-25), with their own documented guarantee:
the same model version, input and settings give the same detections, with any non-determinism
measured and stated. Check every model's licence before adoption (some popular detectors are
AGPL, which is not compatible with our distribution).

### X-21 DICOM medical imaging de-identification

**What.** De-identify DICOM files: header tags (patient name, IDs, dates, institution, device
serials, private tags) and UIDs, with consistent replacement across a study.

**How.** Implement the DICOM PS3.15 Annex E Basic Application Level Confidentiality Profile and
its options (Retain Longitudinal Temporal Information, Retain Patient Characteristics, Clean
Descriptors and others) using `pydicom`. Header tags are structured fields, so the existing
strategies apply: tokenize or hash IDs, date shift per patient (X-13), redact names. UIDs are
replaced deterministically (hash to a new UID under our root) so series and study links survive.
Private tags are removed unless allow-listed. Images with burned-in text are flagged (the
`BurnedInAnnotation` tag and a heuristic) and routed to X-22 later. Cite the standard; compare
against the TCIA de-identification practice and RSNA's CTP anonymizer.

**Who and why.** Hospitals, imaging AI companies and research networks sharing scans for model
training or trials. It is a large, well-defined, regulated need, and it fits the HIPAA disguise
and F47's healthcare packs.

**Difficulty.** L. The profile is long and exact; pixel data handling waits for X-22.

**Placement.** V2. It is the media feature that matches Decoy's architecture: structured fields,
determinism and keys all still apply.

### X-22 Text in images and scans (OCR redaction)

**What.** Find text in images and scanned documents (screenshots, scanned forms, ID cards, DICOM
burned-in annotations) and blur, black out or replace the PII regions.

**How.** OCR with Tesseract (Apache-2.0) or PaddleOCR (Apache-2.0) to get words and boxes, run the
existing detectors on the text, then cover the matched boxes with Pillow or OpenCV. Optional
replacement with synthetic text in a similar font for realistic test images. Presidio's image
redactor uses the same pipeline and is a reference.

**Who and why.** Insurance (claim photos, forms), KYC (ID document images), support (screenshots),
healthcare (scanned records, DICOM burn-in).

**Difficulty.** L. OCR quality on poor scans and measured recall are the hard parts.

**Placement.** V3.

### X-23 Faces and licence plates in images and video

**What.** Detect faces and licence plates and blur, pixelate or replace them with synthetic faces.
Video is the same work frame by frame, plus tracking so a face is covered in every frame.

**How.** Face detection with RetinaFace (Deng et al. 2020) or MediaPipe Face Detection
(Apache-2.0); plate detection with an open-licensed detector. Tracking across frames with a
standard multi-object tracker (SORT or ByteTrack) so missed frames between detections are still
covered. Video decode and encode through FFmpeg (PyAV). Synthetic face swap is optional and later.
GPU acceleration is optional; CPU must still work.

**Who and why.** Autonomous driving and mapping companies (street imagery), retail and security
camera analytics, media companies, and research groups publishing video data under GDPR.

**Difficulty.** XL. Model accuracy, video throughput, tracking and measured recall make this a
program.

**Placement.** V3.

### X-24 Audio redaction

**What.** Remove PII from recordings: find spoken names, numbers and addresses and bleep or silence
them, with the transcript masked too.

**How.** Transcribe with OpenAI Whisper (MIT licence) using word-level timestamps, run the X-11
detectors on the transcript, and replace the matching time ranges with a tone or silence. Voice
anonymization (changing who the speaker sounds like) is still research; the VoicePrivacy
Challenge baselines are the reference if it is ever pursued. Leave it out for now.

**Who and why.** Contact centres (call recordings for QA and training), voice AI companies building
speech datasets, healthcare (dictation).

**Difficulty.** XL. Transcription errors become missed redactions, so recall has to be measured
and stated clearly.

**Placement.** V3 or later. Do only with a customer pulling for it.

---

## 6. Enabler

### X-25 Plugin SDK as the home for heavy extras

**What.** A stable interface for adding strategies, providers, detectors, readers and writers
from separate packages, so the core stays small. This is F40.

**How.** Python entry points (the `importlib.metadata` pattern pytest and others use) to register
plugins; a versioned interface per plugin kind; the plan compiler checks a plugin's declared
capabilities (deterministic or not, chunk-safe or not, which dtypes) the same way it checks
built-in strategies. The media features (X-21 to X-24) and model-based detection (X-11) ship as
first-party plugins with their own extras, so the core install does not pull in PyTorch.

**Who and why.** Us first: it keeps the engine small (modules under 600 lines, a core install
without ML stacks). Then customers who need an in-house identifier format or a proprietary file
type.

**Difficulty.** M. The hard part is a plugin interface stable enough to freeze at GA.

**Placement.** V2, before the media and model features.

---

## Cross-cutting concerns

- **Established methodology.** Each entry names its source pattern; the implementing module must
  cite it in its docstring (engine `CLAUDE.md` core rule).
- **Determinism.** Everything in sections 1 to 4 can keep the current guarantee. Model-based
  features (X-11 zero-shot, X-22 to X-24) need a stated, weaker guarantee; never let them weaken
  the core's.
- **Honest claims.** New privacy and detection features add rows to
  `E:docs/what-we-cannot-prove.md` (recall is measured, not proven; DP covers only what DP
  covers).
- **Dependencies and licences.** New heavy dependencies go behind extras or plugins. Check every
  licence against the engine licence decision (R1-c); avoid AGPL models.
- **Untrusted input.** New parsers (XML, PDF, Office, DICOM, media) are attack surface: bounded
  reads, entity and decompression-bomb limits, and fuzz tests, under the same `fileaccess` rules
  as today.
- **Module size.** New subsystems are packages, not single files, under the 600-line target.

## Questions for the V2/V3 discussion

1. Which of the five recommended V2 core items has a customer pulling today?
2. Do the V1+ items (X-01, X-08 detectors, X-09, X-10) go into a post-CLI-V1 point release or wait
   for V2?
3. Is media (X-21 to X-24) in Decoy's product scope at all, or a separate product on the same
   engine?
4. Should X-16 (generate from a schema) be pulled earlier as a CLI adoption feature?
5. Streaming (X-07): CLI, platform, or both?
