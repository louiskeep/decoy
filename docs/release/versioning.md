# Versioning policy

`decoy-cli` (PyPI dist) follows [Semantic Versioning 2.0.0](https://semver.org/).

`decoy-cli` and `decoy-engine` are published as separate distributions, and each carries its own version number; they bump independently. The CLI's `decoy-engine>=X.Y` dependency pin documents the engine surface it was tested against.

## Bump rules

A release at version `MAJOR.MINOR.PATCH` follows these rules:

| Bump | Trigger |
|---|---|
| MAJOR | Backwards-incompatible change to the public CLI surface: a removed command, a removed flag, a renamed flag, an exit-code re-classification, a YAML schema field rename, a `decoy.cli.exit_codes` constant renamed or removed. Pre-1.0 the MAJOR slot stays at 0; pre-1.0 breaking changes bump the MINOR. |
| MINOR | Backwards-compatible additive change: a new command, a new flag (with a safe default), a new template, a new exit-code constant added (existing values unchanged), a new YAML schema field that defaults to a safe value. |
| PATCH | Bug fix or doc-only change with no surface change: a help-text fix, a typed-error message improvement, a workflow file update that does not change the smoke contract, a CHANGELOG-only commit. |

## Public surface (the contract MAJOR protects)

These are stable across MAJOR boundaries:

1. The set of `decoy <verb>` commands and their flags.
2. Exit-code integer values (the named constants in `decoy.cli.exit_codes` may evolve; the integers may not).
3. The V2 `PipelineConfig` YAML schema (engine-owned; the CLI propagates the engine's contract).
4. The `--json` envelope shape per command (the JSON output that scripts pipe into).
5. The set of bundled templates surfaced by `decoy templates list`.

These are NOT stable and may change across MINOR boundaries:

1. Help-text wording.
2. Spinner text and `--verbose` log line shape.
3. `decoy explain <topic>` body text.
4. Internal modules under `decoy.cli._*`, `decoy.ui.*`, `decoy.templates.*`.
5. The default Faker / Mimesis adoption matrix.

## Pre-1.0

Pre-1.0 (currently `0.X.Y`) the surface is settling. We try to follow MAJOR-equivalent rules using the MINOR slot, but reserve the right to make breaking changes in any 0.X.0 minor bump. The CHANGELOG entry calls out the break explicitly.

The first `1.0.0` release is gated on:

- OSS.2 license flip to Apache-2.0.
- OSS.7 publish pipeline + first real-PyPI green push.
- The release-smoke gate having at least one recorded green run (README §8 R2).
- All Tier-A OSS sprints (OSS.3 through OSS.7) shipped.

## Release process

The mechanical process is owned by OSS.7. Until that sprint lands, releases are by-hand:

1. Run `decoy --version` and confirm the value matches `pyproject.toml`'s `version`.
2. Append a new section to `CHANGELOG.md` under `## [X.Y.Z] - YYYY-MM-DD`.
3. Tag the release on `main` with `git tag vX.Y.Z` and push the tag.
4. Trigger the `release-smoke.yml` workflow on the tag. The smoke gate is required to be green before any publish step.
5. (OSS.7) the trusted-publishing action takes over from here.

## Engine compatibility

`decoy-cli==X.Y.Z` declares `decoy-engine>=A.B` as the minimum engine version it was tested against. A `pip install decoy-cli` resolves to the latest compatible engine in the `A.B+` line. Crossing an engine MAJOR boundary requires a CLI MINOR (additive) or MAJOR (breaking) bump; the CHANGELOG entry names the engine version range explicitly.
