# V1+, V2 and V3 expansion: what it takes, and one product or several

Status: proposal (for the V2/V3 planning discussion; nothing here is scheduled)

Part of the roadmap: [ROADMAP.md](../ROADMAP.md). Path shorthand (`E:`, `C:`, `P:`, vault) is defined there.
Companion to [v2-v3-expansion-candidates.md](v2-v3-expansion-candidates.md), which describes each
candidate feature (X-01 to X-25). This document answers two questions about those candidates:

1. What is the actual ask for each tier: which packages, models, data, infrastructure and skills
   we would add, how hard it is, and roughly how long it takes.
2. Should all of this be one Decoy CLI, or a family of products (for example Decoy Data for tables
   and text, Decoy Optic for media) built on shared technology?

Research for this document (web, 2026-11-06) looked at how established tools package and build the
same capabilities: Microsoft Presidio, the Synthetic Data Vault (SDV), MOSTLY AI, Tonic.ai, Private
AI, John Snow Labs, brighter AI, AssemblyAI, Delphix, K2view, ARX, pydicom and the RSNA tools.
Sources are listed at the end. Vendor claims are marked as such.

---

## Summary

- **V1+ is small and safe.** About 11 to 14 slices of the usual 500 to 700 line size: new readers,
  detectors and generators using small, permissively licensed libraries. No ML models, no new
  runtime. Roughly 2.5 to 3.5 months for one engineer.
- **V2 is a bigger version of the same product.** About 100 slices if we did every V2 candidate,
  or about 40 for the recommended core (plugin SDK, JSON, international, anonymity enforcement,
  copula synthesis, DICOM headers). The core is roughly 9 to 10 engineer-months. It adds
  established statistical methods, more connectors and one small optional ML model (GLiNER).
  The determinism guarantee holds throughout.
- **V3 is a different kind of engineering.** About 85 to 105 slices, plus evaluation datasets,
  GPU-capable CI and ML engineering skill. Its features (OCR, faces, video, audio, streaming) are
  probabilistic or long-running, so they cannot carry the engine's current guarantees. Roughly 2
  engineer-years, and the hard part is measuring accuracy, not writing code.
- **Product shape: one front door, several engines.** Keep one `decoy` CLI, one config language,
  one key and vault model and one evidence format. Ship heavy, probabilistic capabilities as
  separate packages that plug into it: today's engine as **Decoy Data** (tables, files, text,
  documents' text layer, DICOM headers) and a new **Decoy Optic** (pixels: images, scans, video,
  DICOM pixel data). Audio can join Optic or become a third package later. Presidio, SDV and Tonic
  all split this way, for the same reasons.

---

## Part 1. What each tier actually asks for

### How the estimates were made

- **Unit.** One slice is one gated change of about 500 to 700 lines with tests, the size the CLI V1
  roadmap uses (`docs/ROADMAP.md` section 5.3). Estimates assume roughly one slice per engineer-week
  including plan, review gates and merge. **Recalibrate with our measured slice rate before any
  commitment**; the numbers below scale linearly with it.
- **Ranges.** Low is the happy path; high includes one plan revision and one surprise.
- **What is not counted.** Product design, documentation site work, sales engineering, and
  calendar time waiting on owner decisions.
- **Method citations.** Every method named here is an established one. Decoy's rule is to cite
  the method and implement it, not to depend on another product's code where the licence or
  surface does not fit (the engine already does this for SDV's HMA1: "method only, no SDV code").

### Tier V1+: point releases after CLI V1

**The ask.** New readers and detectors on the existing architecture. Nothing changes in how the
engine plans, routes or proves.

| Feature | New packages (licence) | Models | Slices |
|---|---|---|---|
| X-01 Avro and ORC | `fastavro` (MIT); ORC is in `pyarrow` already | none | 2 |
| X-08 International detectors and generators | `phonenumbers` (Apache-2.0); `python-stdnum` is LGPL-2.1, so use it as a format reference and implement the checks in `checksums.py` | none | 4 to 5 |
| X-09 Secrets detection | none required; rule patterns adapted from detect-secrets (Apache-2.0) and gitleaks (MIT), with attribution | none | 2 |
| X-10 Meaning-preserving masks | none; CryptoPAn is a published algorithm on our existing crypto primitives | none | 3 to 5 |
| **Total** | | | **11 to 14** |

**Difficulty.** Low. Each item is independent, so they can ship one at a time.

**Non-code work.** A test corpus of valid and invalid identifiers per country (the published check
algorithms define validity), and false-positive tests for secrets patterns against real-looking
but harmless data.

**Time.** About 2.5 to 3.5 months for one engineer, or 6 to 8 weeks for two.

**Risk.** Low. The main risk is false positives from secrets patterns, which is a tuning problem.

### Tier V2: same product, wider reach

**The ask.** More inputs and targets, established statistical methods, one optional small model,
and the plugin interface that everything heavier will need.

| Feature | New packages (licence) | Models | Slices |
|---|---|---|---|
| X-25 Plugin SDK (F40) | none; Python entry points (`importlib.metadata`), the pattern pytest, Datasette and the `llm` CLI use | none | 4 |
| X-02 JSON and JSONL path masking | none beyond Arrow and Polars; selector follows RFC 9535 (JSONPath) | none | 8 |
| X-03 Excel | `fastexcel` (MIT, read), `openpyxl` (MIT, write) | none | 4 |
| X-04 XML | `lxml` (BSD), `defusedxml` (PSF) | none | 3 |
| X-05 Delta and Iceberg | `deltalake` (Apache-2.0), `pyiceberg` (Apache-2.0) | none | 4 |
| X-06 MySQL, SQL Server, Snowflake, BigQuery | ADBC drivers where available (Apache-2.0); vendor connectors otherwise | none | 16 to 24 |
| X-08 Region disguises | none | none | 3 |
| X-11 Better free-text detection | `gliner` (Apache-2.0), `onnxruntime` (MIT) | GLiNER PII model (Apache-2.0 for `gliner_multi_pii-v1`; one older parent model is CC BY-NC, so pin the exact model) | 8 |
| X-12 Anonymity enforcement (F37) | none; implement ARX's and sdcMicro's methods (ARX is Java, sdcMicro is R and GPL, so neither is a dependency) | none | 8 |
| X-13 Time-series masking | none | none | 4 |
| X-14 Gaussian copula synthesis (F48) | `scipy` (BSD, already present through the stack) | none | 8 |
| X-15 Multi-table synthesis | none | none | 12 |
| X-16 Generate from a schema | `sqlglot` (MIT) | none | 4 |
| X-17 Edge-case data (F46) | none; Big List of Naughty Strings (MIT) as data | none | 4 |
| X-19 Metadata scrubbing (F38) | `pikepdf` (MPL-2.0), `python-docx` (MIT), Pillow (HPND) | none | 2 |
| X-21 DICOM headers | `pydicom` (MIT) | none | 8 |
| **Total, all V2 candidates** | | | **about 100 to 110** |
| **Recommended V2 core** (X-25, X-02, X-08 disguises, X-12, X-14, X-21) | | | **about 39** |

**Difficulty by kind.**

- **Connectors and formats (X-02 to X-06): medium, mostly breadth.** Each database is its own
  test lane (container in CI) and its own type-mapping report. Delphix's published connector list
  shows how long this tail is for a mature vendor; we should pick databases by customer pull, not
  aim for coverage.
- **Statistical methods (X-12, X-14, X-15): medium to hard, mostly correctness.** The methods are
  well published (Sweeney 2002; Machanavajjhala et al. 2007; Li et al. 2007; Domingo-Ferrer and
  Mateo-Sanz 2002; Patki et al. 2016). The hard parts are whole-table memory for X-12 and X-15,
  categorical handling in X-14, and an honest risk report.
- **Free-text model (X-11): medium.** The library is easy to adopt. Proving recall needs a
  labelled corpus; the standard clinical one (n2c2 2014 de-identification) needs a data use
  agreement, so plan the paperwork early.
- **DICOM headers (X-21): medium, mostly standard-following.** PS3.15 Annex E is long and exact.
  Free tools differ in how fully they follow it (Aryanto et al. 2015 compared ten), and the
  standard's editor warns that over-aggressive defaults make data unusable. Validate against a
  public benchmark (the MIDI-B DICOM de-identification benchmark on TCIA) rather than our own
  judgement.

**Infrastructure.** Database containers in CI (MySQL, SQL Server; Snowflake and BigQuery need
paid test accounts and stored credentials). No GPU. The plugin SDK adds a "core without extras"
CI lane to prove the core install stays light.

**Guarantees.** Everything in V2 except GLiNER keeps byte-for-byte determinism. GLiNER is
deterministic for a pinned model on the same runtime, the same rule spaCy already follows in
`E:src/decoy_engine/detection/ner.py`.

**Time.** All candidates: about 2 to 2.5 engineer-years. Recommended core: about 9 to 10
engineer-months, so a two-engineer team could ship it in about 5 months.

### Tier V3: new kinds of engineering

**The ask.** ML models for vision and speech, true document redaction, a long-running streaming
service, and learned sequential synthesis. These change what the product can promise.

| Feature | New packages (licence) | Models (licence, size) | Slices |
|---|---|---|---|
| X-20 Document redaction | `pdfminer.six` or `pdfplumber` (MIT) for text with positions; `pikepdf` (MPL-2.0) to remove content; `python-docx` (MIT). **Avoid PyMuPDF**: AGPL unless a commercial licence is bought from Artifex | none (reuses X-11) | 10 |
| X-22 OCR redaction | Tesseract (Apache-2.0) or PaddleOCR (Apache-2.0), `onnxruntime` (MIT), OpenCV (Apache-2.0) | PP-OCRv5 mobile models are a few MB; server detection is about 84 MB | 10 |
| X-23 Faces and plates, images and video | OpenCV (Apache-2.0), PyAV (BSD) with an LGPL FFmpeg build (avoid GPL codecs such as x264), a tracker (SORT or ByteTrack, MIT) | YuNet face detector (MIT, under 1 MB, in OpenCV Zoo). **Avoid** Ultralytics YOLO (AGPL-3.0, which Ultralytics says also covers models you train yourself) and InsightFace's pretrained models (non-commercial research only) | 20 to 25 |
| X-24 Audio redaction | `faster-whisper` (MIT) on CTranslate2 | Whisper (MIT): tiny 39M parameters up to large 1.55B; about 1 GB to 10 GB of memory | 12 to 15 |
| X-07 Streaming and CDC | `confluent-kafka` (Apache-2.0); Debezium event format | none | 15 to 20 |
| X-18 Sequential synthesis | none for the Markov version | none, or a small autoregressive model (MOSTLY AI's open-source TabularARGN is a reference design) | 10 to 15 |
| X-06 MongoDB | `pymongo` (Apache-2.0) | none | 8 |
| **Total** | | | **about 85 to 105** |

**Difficulty by kind.**

- **Accuracy you have to measure (X-22 to X-24).** Detection models miss things. A missed face or
  name is a leak, so recall must be measured on labelled data and stated. Two public examples
  show the gap: John Snow Labs' own 2026 poster reports DICOM pixel de-identification at
  precision 1.0 but recall 0.714 on 70 MIDI-B files, and a 2024 study found Whisper invented
  text in about 1 percent of transcriptions. Building the evaluation sets is as much work as
  building the features.
- **Evaluation data licences.** Many face and plate benchmarks are research-only. We need data we
  are allowed to test a commercial product against, or our own labelled set. Budget for it.
- **Video throughput.** Frame-by-frame detection is slow on CPU. A GPU path is optional but
  realistic for customers with large volumes, which means GPU-capable CI or at least a nightly GPU
  lane.
- **Package weight.** A CPU-only PyTorch install is roughly 200 MB to download and far larger once
  installed; CUDA builds run to gigabytes. ONNX Runtime with exported models is much lighter, so
  the default should be ONNX models on CPU, with PyTorch only where unavoidable.
- **Streaming (X-07)** is a service: offsets, back-pressure, restarts and monitoring. It belongs
  with the platform more than the CLI.

**New skills.** Computer vision and speech evaluation, model export and quantisation, video
encoding, and streaming operations. Today's team skills (data engineering, crypto, statistics)
cover the rest of the roadmap but not these.

**Guarantees.** The core guarantee (same input, config and key give the same bytes) does not hold
for pixel and audio redaction across hardware. V3 needs a second, documented guarantee: same model
version, input and settings give the same detections on a stated runtime; recall is measured on a
named dataset and published. `E:docs/what-we-cannot-prove.md` grows a media section.

**Time.** About 2 engineer-years of building, plus evaluation data work, by a team that includes
at least one engineer with vision or speech experience.

### Side by side

| | V1+ | V2 (recommended core) | V2 (all) | V3 |
|---|---|---|---|---|
| Slices | 11 to 14 | about 39 | 100 to 110 | 85 to 105 |
| Engineer time | 2.5 to 3.5 months | 9 to 10 months | 2 to 2.5 years | about 2 years plus data work |
| New dependency class | small pure libraries | connectors, scipy, one small model | same | vision and speech models, video codecs, Kafka |
| Determinism | unchanged | unchanged (model pinned) | unchanged (model pinned) | second, weaker guarantee |
| GPU | no | no | no | optional, likely for video |
| New skills | none | statistics depth | statistics, many databases | vision, speech, streaming |
| Main risk | false positives | whole-table memory, honest risk report | breadth and maintenance | missed detections, model licences |

---

## Part 2. One Decoy, or a Decoy ecosystem?

### How established tools split

| Tool | Shape | Why it matters for us |
|---|---|---|
| Microsoft Presidio | Separate packages: `presidio-analyzer` (detection), `presidio-anonymizer` (operators), `presidio-image-redactor` (images and DICOM pixels, needs Tesseract), `presidio-structured` (tables and JSON, alpha) | The closest precedent. Detection is shared; the image package carries the OCR dependency so text users never install it. Note its DICOM support only covers burned-in pixels, not headers: the opposite half from where Decoy is strong |
| Synthetic Data Vault (SDV) | `sdv` bundles separately installable `copulas`, `ctgan`, `rdt` (transforms), `sdmetrics` (quality) and `deepecho` (sequences) | Heavy deep-learning models live in their own packages; the quality library is usable on its own |
| Tonic.ai | Separate products: Structural (databases), Textual (unstructured text and files), Fabricate (schema-first synthesis, acquired from the Mockaroo team in 2025), Ephemeral (temporary environments) | Splits by buyer and data type, sold under one brand |
| Private AI / Limina | One container and API covering text, documents, images and audio (vendor claims 50+ entity types, 52 languages) | Shows a single detection core can serve every modality, but as a hosted service, not a CLI |
| John Snow Labs | Healthcare NLP and a separate Visual NLP product for PDFs, images and DICOM | Medical imaging sold apart from text, to the same healthcare buyer |
| brighter AI | Image and video only: blur and generative face and plate replacement | Media anonymization is a standalone business with its own buyers (automotive, mapping, video analytics) |
| AssemblyAI | Audio redaction inside a speech-to-text API: transcribe, find PII, beep or silence by word timestamps | Audio redaction is a feature of a speech product, not of a data product |
| LangChain | A uv monorepo of independently versioned packages: `langchain-core` plus partner packages | Split so integrations with different dependencies, tests and release pace do not slow the core |
| Delphix, K2view | One platform; Delphix documents limited unstructured support, K2view advertises images and PDFs | The enterprise masking incumbents are tabular-first; media is a differentiator, not table stakes |

The pattern: **detection and keys are shared; heavy modalities ship apart.** Nobody puts OCR,
vision models and video codecs in the same install as a tabular masking engine.

### The three options

**Option A: one CLI, one engine, optional extras** (`pip install decoy-engine[media]`).

- For: simplest for users and for us; one release, one version.
- Against: the engine's test, licence and size gates would have to cover PyTorch-class
  dependencies; the engine's determinism guarantee gets an exception list; every engine release
  waits on media tests; licence exposure from any model touches the core package.

**Option B: one front door, several engines** (recommended).

- One `decoy` CLI, one config language, one key and vault model, one evidence and reason format.
- Engines as separate packages that plug into the CLI through the plugin SDK (X-25):
  - **Decoy Data**: today's `decoy-engine`. Tables, files, databases, JSON and XML, free text,
    the text layer of documents, DICOM headers, synthesis. Deterministic.
  - **Decoy Optic**: a new package, depends only on the engine's public API. Images, scans,
    video, DICOM pixel data. Model-based, with its own documented guarantee.
  - **Audio**: inside Optic at first (it shares the model runtime and the measured-recall
    guarantee), split out only if it grows its own buyers.
- The CLI discovers installed engines (`decoy optic ...` appears when `decoy-optic` is installed),
  the way the `llm` CLI and Datasette load plugins and git and kubectl find subcommands.
- For: the core stays small, deterministic and fast to release; Optic can carry different model
  licences, GPU CI and release pace; buyers can buy what they need; the same key masks a patient
  ID in a claims table and in a DICOM header, so joins across modalities still work.
- Against: two packages to version and test together; the plugin interface must be stable before
  Optic ships (that is X-25, which is a V2 item anyway).

**Option C: separate products sharing a brand.**

- For: clear market positioning per buyer.
- Against: duplicates keys, vault, evidence and config; loses cross-modality consistency, which is
  the strongest reason to buy them from one vendor; too much overhead for the team's size.

### Recommendation

Option B. In practice:

1. **Now (V2):** build the plugin SDK (X-25) and keep everything else in the current engine.
   DICOM headers (X-21) belong in Decoy Data: they are structured fields and keep every current
   guarantee.
2. **When the first pixel feature starts (V3):** create `decoy-optic` as its own repo and package.
   It imports only the engine's public API (the internal-import sentry already enforces the
   boundary). One `decoy dicom` command uses both engines: Data for headers, Optic for burned-in
   pixels, the split John Snow Labs also describes.
3. **Shared pieces stay in the engine:** detectors (text found by OCR or speech goes through the
   same detectors), the key hierarchy (HKDF), the vault, reasons and evidence.
4. **Licences per package:** the engine licence decision (R1-c: Apache-2.0 or BUSL-1.1) can
   differ for Optic, which may need to be stricter because of model licences.
5. **Naming is a product decision.** "Decoy Data" and "Decoy Optic" work as product names over
   package names (`decoy-engine`, `decoy-optic`); the CLI stays `decoy`.

### What would change the recommendation

- If no customer asks for media within V2, stop at step 1. The plugin SDK pays for itself anyway.
- If a customer needs media first and fast, Presidio's image redactor or an established vendor
  API can be wrapped as an Optic plugin, but check licences and data-residency first, and never
  route customer data to a hosted API without explicit opt-in.
- If the team grows a separate ML group, Option C becomes more reasonable for Optic alone.

---

## Questions for the owner

1. Do we confirm Option B (one CLI, Decoy Data and Decoy Optic engines) as the direction?
2. Is the V2 recommended core (about 39 slices) the right scope, and is there customer pull for
   any of its items?
3. For V3 media, do we hire or contract vision and speech experience, or defer media until then?
4. Who owns evaluation data: buying or licensing datasets, data use agreements (n2c2), and
   building our own labelled sets?
5. Does Optic share the engine licence, or follow its own?

## Sources

Packaging and ecosystem:

- [Presidio Image Redactor](https://microsoft.github.io/presidio/image-redactor), [presidio-image-redactor on PyPI](https://pypi.org/project/presidio-image-redactor/)
- [Presidio structured](https://microsoft.github.io/presidio/structured), [presidio-structured on PyPI](https://pypi.org/project/presidio-structured)
- [SDV Enterprise: what's in the package](https://docs.sdv.dev/sdv-enterprise/installation/whats-in-the-package)
- [Tonic.ai platform overview](https://www.tonic.ai/assets/platform-overview), [Tonic.ai product updates May 2025](https://www.tonic.ai/blog/tonic-ai-product-updates-may-2025), [Tonic.ai product updates October 2025](https://www.tonic.ai/blog/tonic-ai-product-updates-october-2025)
- [LangChain architecture announcement](https://blog.langchain.com/the-new-langchain-architecture-langchain-core-v0-1-langchain-community-and-a-path-to-langchain-v0-1), [LangChain repo structure](https://python.langchain.com/docs/contributing/repo_structure)
- [How to set up a Python monorepo with uv workspaces](https://pydevtools.com/handbook/how-to/how-to-set-up-a-python-monorepo-with-uv-workspaces/)
- [Private AI text product](https://private-ai.com/products/text), [Limina on Capterra](https://www.capterra.in/software/1106821/Limina)
- [John Snow Labs Visual NLP](https://johnsnowlabs.com/visual-nlp), [De-identifying DICOM files with Visual NLP](https://www.johnsnowlabs.com/de-identifying-dicom-files-a-step-by-step-guide-with-john-snow-labs-visual-nlp/), [ICHI 2026 poster](https://www.johnsnowlabs.com/wp-content/uploads/2026/05/poster_id124_ichi2026.pdf)
- [brighter AI product](https://brighter.ai/product/)
- [AssemblyAI PII redaction](https://assemblyai.com/docs/pii-redaction)
- [Delphix data source support](https://maskingdocs.delphix.com/Getting_Started/Data_Source_Support/), [K2view data masking](https://k2view.com/platform/data-masking-tools)
- [NVIDIA acquires Gretel (TechCrunch)](https://techcrunch.com/2025/03/19/nvidia-reportedly-acquires-synthetic-data-startup-gretel)
- [MOSTLY AI open-source synthetic data SDK paper](https://arxiv.org/html/2508.00718v2), [mostlyai-engine on PyPI](https://pypi.org/project/mostlyai-engine/2.5.0/)

Methods and standards:

- [ARX Data Anonymization Tool](https://bioinformaticshome.com/db/tool/arx/)
- [pydicom deid](https://github.com/pydicom/DEID)
- [Free DICOM de-identification tools in clinical research (Aryanto et al.)](https://typeset.io/pdf/free-dicom-de-identification-tools-in-clinical-research-1j44yd9quk.pdf)
- [Clunie, letter on de-identification defaults (European Radiology)](https://journals.myesr.org/eur-radiol/?p=748)

Models, libraries and licences:

- [Ultralytics licence](https://ultralytics.com/license)
- [InsightFace tutorial and licence notes](https://github.com/deepinsight/insightface/wiki/Tutorial)
- [OpenCV Zoo YuNet](https://github.com/opencv/opencv_zoo/blob/main/models/face_detection_yunet/README.md)
- [deface (ORB-HD)](https://github.com/ORB-HD/deface)
- [GLiNER multi PII v1 model card](https://huggingface.co/urchade/gliner_multi_pii-v1)
- [OpenAI Whisper](https://github.com/openai/whisper), [faster-whisper](https://pypi.org/project/faster-whisper/0.9.0)
- [PaddleOCR ONNX models](https://huggingface.co/monkt/paddleocr-onnx)
- [PyMuPDF features and licensing](https://pymupdf.readthedocs.io/en/latest/about.html), [pikepdf on PyPI](https://pypi.org/project/pikepdf)
- [PyTorch forum: CPU wheel size](https://discuss.pytorch.org/t/large-cpu-file-size/112709)
- [Whisper hallucination study coverage](https://www.futuremedicine.com/articles/study-finds-openais-popular-transcription-tool-whisper-hallucinates-text)

Facts from general knowledge, not re-checked in this research pass: the licences of `fastavro`,
`phonenumbers`, `python-stdnum` (LGPL), `fastexcel`, `openpyxl`, `lxml`, `deltalake`, `pyiceberg`,
`sqlglot`, `pydicom`, Tesseract, OpenCV, PyAV, `confluent-kafka` and `pymongo`; that the n2c2 2014
corpus needs a data use agreement; and the MIDI-B benchmark's hosting on TCIA. Confirm each before
adoption, as the dependency licence check requires anyway.
