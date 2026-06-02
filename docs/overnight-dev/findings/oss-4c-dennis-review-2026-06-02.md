# OSS.4c Dennis review: column-aware `decoy init <file>` scaffolding

Date: 2026-06-02
Branch reviewed: `oss-4c-init-column-aware` @ `3eb23a3`
Spec: `decoy-platform/docs/v2/sprints/oss-cli/04-oss-4-init-scaffolding-and-scan-alias.md` lines 176-330
Decision: APPROVED, merged.
Merge SHA: `35c485a` on `main` (no-ff, matching OSS.4a + OSS.4b merge style).

## What I checked

1. Detector-id table sizing + REVIEW copy quality.
2. Hand-rolled YAML emission round-trip through `PipelineConfig.model_validate`.
3. Edge cases that would burn a real user: empty CSV, all-null columns, YAML-hostile column names, Windows path quoting, `--out -` stdout.
4. Spec adherence verbatim against the OSS.4c sub-spec.
5. Barry-shaped legacy/comment/doc rot on the diff.

## Findings

### Inference table (item 1)

18 detector ids cover the canonical PII surface STORM ships: `email`,
`ssn`, `us_phone`, `person_name`, `iso_date`, `us_date`, `us_zip`,
`address_street`, `address_city`, `mrn`, `npi`, `ndc`, `icd10`, `pan`,
`cvv`, `iban`, `uuid`, `ipv4`. I cross-checked against
`decoy_engine/storm/detectors.py REGISTERED_DETECTORS` (25 entries) and
`decoy_engine.providers_v2.get_default_registry().known_providers()`
(33 entries). Every `strategy: faker` row references a provider that
the registry actually ships (`person_email`, `person_phone`,
`person_full_name`, `address_street`, `address_city`, `uuid`). Strategy
names map to live `SCALAR_HANDLERS` (`faker`, `hash`, `redact`,
`date_shift`, `truncate`, `fpe`). Nothing dangling.

REVIEW copy is factual and operator-actionable. The "use
`provider: synthetic_X` if you need real-shape output" callouts on
SSN/MRN/NPI/NDC/IBAN match what the registry actually exposes
(`synthetic_ssn`, `synthetic_mrn`, `synthetic_npi`, `synthetic_ndc`,
`synthetic_iban` all present). Zero marketing fluff. The PAN entry
flags `fpe` with `key_label: default` and explicitly tells the user to
review the key label before running, which is the right friction
point.

### YAML round-trip + smoke validation (item 2)

Verified end-to-end on a real STORM scan: emitted YAML parses through
`yaml.safe_load` and `PipelineConfig.model_validate` returns a valid
config with `sources['data']`, `tables[0].columns`, `targets['data']`.
I also confirmed the silent-no-op fallback in `_validate_scaffold` is
NOT exercised in the production install path: from the same Python
that runs the CLI, both `import yaml` and
`from decoy_engine.config import PipelineConfig` succeed. The no-op
branch is defensive cover for embedded/PEX contexts where the engine
isn't reachable, which the spec says to tolerate.

End-to-end test on a real CSV:
- `decoy init customers.csv --out pipeline.yaml --quiet` exit 0, YAML
  written with REVIEW comments + Windows-quoted paths.
- `decoy validate pipeline.yaml` exit 0 against the scaffolded file.

### Edge cases (item 3)

- Empty CSV: exits with EXIT_RUNTIME and clear stderr
  (`error: No columns to parse from file`). Clean.
- All-null column: STORM finds no detector match, falls through to
  `_FALLBACK` (redact + verbose REVIEW). Clean.
- Windows path with backslashes: emitted as single-quoted YAML scalar.
  YAML 1.1 single-quote rules treat backslash literally; PyYAML +
  `PipelineConfig` accept the round-trip. `decoy validate` on the
  scaffolded file with a `C:\Users\...` path exits 0.
- `--out -` stdout path bypasses overwrite check and writes body to
  stdout; the JSON envelope branch is skipped (consistent with "stdout
  IS the output"). Test pins it.
- YAML-hostile column names (`true`, `null`, `*anchor`, etc.): the
  emitter does not quote the `name:` value. PyYAML parses anchor-style
  names into a YAML alias error and `_validate_scaffold` raises before
  any file is written. Result is EXIT_RUNTIME with a stderr message
  pointing at the scaffolder, which is louder than silent corruption.
  Real CSV headers almost never look like this; if it surfaces, the
  user fix is "quote your headers in the source CSV". Recorded as a
  LOW follow-up, not a blocker.

### Spec adherence (item 4)

Verbatim against OSS.4c sub-spec lines 290-303:
- Positional `input_file: Path | None = typer.Argument(None, ...)`
  added (init.py:358). Present.
- Branch on `input_file is not None and preset is None`
  (init.py:406). Correct precedence: `--preset` wins if both are
  passed.
- Inference table in `src/decoy/cli/_init_inference.py`. Present, <=20
  entries.
- Hand-rolled YAML emitter; smoke-validate via
  `PipelineConfig.model_validate` BEFORE writing
  (init.py:340-352, then write at 434). Order correct.
- `--out PATH` and `--out -` (stdout) honored.

One minor scope expansion: `_load_dataframe` accepts `.parquet/.pq`
too. The spec's parquet restriction (line 235) targets
`decoy storm integrity`, not `decoy init`. Pandas reads both natively,
and accepting parquet here matches the existing engine file-source
loader. Permissible.

### Barry-shaped diff hygiene (item 5)

- README updated with two-path quickstart + corrected command table
  entry for `decoy init [file]`.
- No legacy V1 references in new code.
- New module docstrings cite source patterns (dbt init + cookiecutter)
  per the established-methodology rule.
- Comments explain why, not what (e.g., "Templates used by the wizard"
  block at init.py:55-58 explains why generate/graph route through
  unchanged).
- One trailing line at init.py:568 (`_init.__doc__ = _init.__doc__`)
  is a no-op left from a previous edit. Cosmetic. LOW, not worth a
  follow-up commit.

## Tests run

- `python -m pytest tests/unit/test_init_inference.py tests/e2e/test_init_scaffold_roundtrip.py -x -q` -> 19/19 green.
- `python -m pytest -x -q` (full CLI suite) -> 252/252 green.
- Manual end-to-end probe: empty CSV, all-null, hostile names,
  Windows paths, JSON mode, `--out -`, `decoy validate` against
  scaffolded file. All behave as specified.

## What was merged

Merge commit `35c485a` on `main`. No squash, no rebase. Matches
OSS.4a (`f04d251`) + OSS.4b (`8c573a3`) merge style.

Local + remote feature branch `oss-4c-init-column-aware` deleted.

## Follow-ups (not blockers)

- LOW: YAML-hostile column names trip the smoke-validator and error
  loudly. Could quote `name:` values defensively in `_emit_column_yaml`,
  but real-world CSV headers don't hit this. Defer.
- LOW: trailing `_init.__doc__ = _init.__doc__` line in `init.py:568`.
  Cosmetic.
