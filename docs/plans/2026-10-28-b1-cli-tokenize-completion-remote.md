# B-1 CLI tokenize/detokenize + local vault: completion plan for a remote worker

Status: shipped (merged via PR #64)
Feature: F09 (cross-job identity domains), CLI surface, single-operator local.
Tier: R2 (security-sensitive: a reversible PII vault, cleartext at rest). Plan gate chain: Dennis -> Codex.
(NOT crypto-MAJOR: token derivation is engine-owned; the CLI side is SQLite persistence + file perms, no crypto design. No Gemini stage.)
Branch to continue: `claude/bold-mendel-q1d3ot` (repo `decoy`, tip `3640ddc`).
Author: orchestrator (local). Executor: remote claude.ai/code worker.
Created: 2026-10-28.

Rules consulted: `~/dev-rules/00-universal.md`, `~/dev-rules/development-loop.md`,
`~/dev-rules/risk-and-exceptions.md`, `~/dev-rules/security.md`,
`~/dev-rules/config-secrets-and-supply-chain.md`, `~/dev-rules/testing.md`,
`~/dev-rules/feature-dev.md`, `~/dev-rules/api-and-compatibility.md`.

## 1. Problem and definition of done

The `decoy tokenize` / `decoy detokenize` CLI commands and a local SQLite token vault
are built on the branch and passed one review round. A round-2 Codex gate returned
NO-GO on three security/correctness findings, none of which has a test. This plan
scopes those three fixes plus the gate to merge-ready. No engine change, no rebase
(the branch is current with `main`).

**Definition of done.** The three findings are fixed at the root, each with a
regression that fails on the pre-fix code; the tokenize/detokenize round-trip and
fail-closed behavior hold; the local ci-mirror (ruff + pytest) is green against an
installed `decoy-engine` from `main`.

## 2. Current state (built on the branch, do NOT rebuild)

- `src/decoy/cli/_token_vault.py`: `LocalTokenVault`, a SQLite `(namespace, plaintext)
  <-> token` store implementing the engine `TokenVaultWriter` protocol
  (`lookup_existing` / `put`) plus a CLI-local `reverse`. Buffered writes, durable only
  on explicit `commit()` (a failed run leaves no partial mapping). Fail-closed opens:
  `vault_not_found`, `vault_not_a_token_vault`, `vault_schema_mismatch`,
  `vault_token_conflict`.
- `src/decoy/cli/tokenize.py`: the `tokenize` + `detokenize` Typer commands. tokenize
  runs `run_pipeline(..., token_vault_writer=...)`, writes outputs, then commits;
  detokenize reads the tokenized file and reverses every tokenize column, fail-closed
  on any token miss.
- `src/decoy/cli/explain.py` (`decoy explain tokenize`), `__main__.py` wiring, docs,
  and tests (`tests/unit/test_token_vault.py`, `tests/e2e/test_tokenize_cli.py`).

## 3. Established solutions (surveyed; design follows them)

- Token derivation is the ENGINE's keyed HKDF-SHA256 `derive` + NFC normalization; the
  CLI never derives tokens, it persists/looks up what the engine hands to `put` /
  `lookup_existing`. No hand-rolled crypto (engine `CLAUDE.md` rule).
- Mask-secret handling is the engine keyprovider (DE-02); the CLI refuses to emit
  unkeyed tokens on a pre-DE-02 engine.
- Persistence is stdlib `sqlite3`. The vault is NOT encrypted at rest (single-operator
  local design); `0600` file permissions are the at-rest protection (fix (a)), which is
  the standard POSIX approach for a secret-bearing local file.

## 4. Remaining work: the three NO-GO fixes (each with a test)

**(a) Vault file permissions `0600` (security).** `LocalTokenVault.__init__` creates the
parent with `mkdir(parents=True, exist_ok=True)` and opens `sqlite3.connect(path)` with
no `chmod`, so the vault lands under the process umask (typically world-readable). The
vault is the one place the re-identifying `plaintext -> token` map lives, in cleartext,
so perms are the only at-rest protection. Fix: create the vault file `0o600` and its created parent dir `0o700`, restricting
BEFORE any schema or data is written. Implementation caveats: chmod the FILE
immediately after `sqlite3.connect` creates it and before `_ensure_schema` (do NOT
rely on secrets arriving only at the caller's `commit()`: SQLite can spill dirty pages
mid-transaction, so protection must precede ALL schema/data operations, and
self-healing cannot undo a prior exposure); a failed chmod must ABORT before any
schema/data write; chmod `0o700` ONLY the parent dir THIS call created (check
`parent.exists()` before `mkdir`, never a pre-existing possibly-shared user dir); run
the file chmod on every create-path open so it repairs a vault a prior buggy build left
`0644`. Test (must FAIL on pre-fix code, so CONTROL the umask: a runner at umask `0077`
already yields `0600` and would hide a missing chmod): create under a controlled umask
`0022` in an isolated subprocess and assert the file is `0600`; separately reopen an
explicitly `0644` vault and assert it is repaired to `0600`; assert a newly created
parent is `0700` and a pre-existing parent is unchanged; assert a chmod failure aborts
before schema/data. POSIX-guarded (CI is Linux).

**(b) Output path collision + silent overwrite (correctness).** Correct the mechanism
first: `Path("export.jan.csv").with_suffix(".detokenized.csv")` PRESERVES `.jan`
(gives `export.jan.detokenized.csv`); `with_suffix` replaces only the final suffix, it
does NOT truncate. The real defects are (1) two inputs differing only in final
extension collide (`a.csv` and `a.tsv` both map to `a.detokenized.csv`), and (2) the
default silently OVERWRITES a pre-existing output (data loss on re-run). Fix: refuse to
overwrite an existing default output (coded error, no clobber). That closes BOTH
hazards with ZERO naming change: the colliding second input fails closed instead of
overwriting, and the documented `<stem>.detokenized.<ext>` name, the 6 e2e assertions,
the epilog example, the `--output` help default, and `docs/cli-reference.md` all stay
intact. Tests (each MUST fail on pre-fix code, both inputs otherwise valid): (i) two inputs
sharing a stem but differing in final extension -> the second is refused, no clobber
(use CSV-encoded content for the `.tsv` fixture, since the reader treats every
non-Parquet extension as CSV); (ii) an existing default output -> refused with a coded
error. Assert the refusal exit/code AND that the first output's bytes are unchanged. Do
NOT use the "dotted name keeps all segments" assertion, it passes on pre-fix code and
locks nothing. Path traversal /
absolute paths are considered and dismissed (single-operator, user-supplied paths on
their own box). A distinct output NAME is explicitly NOT chosen here; if ever wanted it
is a separate change that must also update the 6 e2e assertions, the epilog example,
the `--output` help default string, and `docs/cli-reference.md`.

**(c) detokenize require-all-columns (fail-closed).** A tokenize column declared for the
target table but absent from the input file is recorded `status="column_missing"` and
skipped, and the run still SUCCEEDS and writes output, silently leaving a configured
tokenize column unreversed. Fix: fail closed (no output written) when any
config-declared tokenize column for the target table is missing from the input,
matching the existing fail-closed-on-any-token-miss posture. Test: a file missing a
declared tokenize column produces no output and a coded error (use a valid vault and
resolvable remaining columns so the regression fails for the intended missing-column
reason, not an unrelated error).

Rebase: none (merge-base is `origin/main` tip). Gate: local ci-mirror (ruff +
pytest), GitHub CI is billing-blocked.

## 5. Observable behavior, failure modes, acceptance

- **Round-trip:** tokenize replaces every `strategy: tokenize` column with the engine
  surrogate and writes `(namespace, plaintext) -> token`; detokenize reverses by
  `(namespace, token) -> plaintext` from the same vault and restores originals (CSV all
  text, Parquet by extension).
- **Reversibility, fail-closed:** gated only by possession of the local vault file (no
  user model). No output on missing vault, non-vault file, schema mismatch, any token
  miss, or (fix c) any missing declared column.
- **Determinism / namespace:** same `(plaintext, namespace)` -> same token (vault
  authoritative, stable across runs); same plaintext under two namespaces -> two
  distinct, unlinkable tokens; an explicit `namespace:` is required per tokenize column
  (engine `tokenize_requires_namespace`, CLI reports it before touching the vault).
- **Mask secret required:** tokenize fails closed `tokenize_requires_secret` without a
  resolvable `--mask-secret` / `global_settings.mask_secret_ref` (unkeyed tokens would
  be forgeable offline).
- **Secrets/values stay out of diagnostics:** never leak plaintext, a token, the mask
  secret, or a data value into logs or error text. A file PATH in user-facing output
  (the written-output location) is legitimate and not a leak; the rule targets
  diagnostic echoing of input values. Current `tokenize.py` emits paths in JSON /
  success / error and detokenize renders `str(ValidationError)` without tokenize's
  raw-secret-reference guard, so add sentinel assertions across BOTH verbs' human AND
  JSON error paths, including an invalid secret-reference config and the three new
  failure modes, and redact any exposed value before claiming the no-leak acceptance.
- **Schema-version mismatch:** a vault with a mismatched `schema_version` yields no
  output and a coded error (the inspected vault suites lack this case).

## 6. Pinned guarantee and non-goals

**Guarantee.** A single-operator local tokenize/detokenize round-trip whose reverse
mapping is a `0600` SQLite vault, fail-closed on every miss, with engine-derived
deterministic namespace-scoped tokens.

**Recovered-output scope (state it honestly).** The detokenize recovered file is
itself cleartext PII (the restored originals), written at the default umask like every
other `decoy` output; Decoy does not chmod run outputs, so B-1 does not chmod this one
either. The at-rest doc note must say plainly that the operator protects the recovered
output, so the 0600 vault and the world-readable recovered file are not a silent
inconsistency. (Applying 0600 to the recovered file too is an acceptable alternative,
but the honest note is the proportionate V1 choice given single-operator local trust.)

**Non-goals.** No multi-user or admin-only de-tokenize authorization (that is the
platform vault, B-6); no encryption at rest of the local vault (0600 is the V1
mitigation, stated honestly in the docs); no engine change; no new engine pin beyond
the existing `decoy-engine>=0.7.0` floor. A review finding outside this guarantee is a
recorded follow-up, not a blocker.

## 7. Design notes

Three localized fixes in two existing modules (`_token_vault.py`, `tokenize.py`); no
new structure or abstraction. House style on touched code (comments explain why, single
purpose). The `0600`/`0700` restriction belongs in `LocalTokenVault.__init__` before
first write; the output-path fix is in detokenize's default-output computation; the
require-all-columns fix is in detokenize's per-column loop (the same place that already
drops `column_missing`). Carry-forward (not in the three-fix scope, do if touching the
file): the `_token_vault.py` docstring says "engine 0.15.0" while the pin floor is
`>=0.7.0`; align it to 0.7.0 / the A-8 seam so it does not read as "needs 0.15.0".

## 8. Remote-worker scope (phase 0) and hand-back

Phase 0 = the three fixes + their tests + the honest-at-rest doc note (vault AND
recovered output), on `claude/bold-mendel-q1d3ot`. No engine edit, no pin change, no
rebase.

**Install the engine for tests (access caveat).** Runtime AND tests import
`decoy_engine`, which is a PRIVATE, non-PyPI repo (`louiskeep/decoy-engine`, the
commercial engine; the CLI is only source-available). You need read access / a token
for that repo: install it editable from the repo at `main` (it carries the A-8
token-vault seam + the DE-02 `keyprovider` the CLI probes) plus the `dev` extra. If you
cannot authenticate to that repo, do NOT silently skip the tests: hand back BLOCKED and
say so in the PR, naming which tests ran in-env vs deferred to ORCHESTRATOR-RUN
verification (GitHub CI is billing-blocked, so the orchestrator runs the local
ci-mirror). Record the exact engine SHA you tested against, and never treat a deferred
check as green. Then run the local ci-mirror (ruff + pytest unit + e2e).

Push your branch and open a PR against `main`; do NOT merge. The orchestrator runs the
code gate (Dennis -> Codex) and merges on green.
