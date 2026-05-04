# Decoy rename — `forge` CLI

This repo's slice of the **Forge → Decoy** rebrand. Scope here is the public CLI only; engine internals are handled in `forge-engine/DECOY_RENAME.md`.

## Why

The name "Forge" is heavily occupied in developer tooling (GitHub Forge, Laravel Forge, Forge Rock). Marketing + tech lead chose **Decoy** because it captures both core functions — masking and generation — in one word. A decoy looks real but isn't; that's exactly what this tool produces.

## Cross-cutting rules (apply everywhere)

- **Do NOT rename the word "mask" globally.** "Mask" is the locked taxonomy term for a single field-level transform inside a Disguise. Only rename when it refers to the *bundle* (those become Disguises). The CLI deals in Masks; it does not own the Disguise concept.
- **HIPAA, never HIPPA.** Add a grep gate before tagging a release.
- **No per-row pricing language anywhere.** Phrase: "flat pricing" or "no per-row fees."

## Changes in this repo

### Package + entry point
- `pyproject.toml`: `name = "forge"` → `name = "decoy"`. Update `[project.scripts]` so the console script `forge` becomes `decoy`.
- `src/forge/` → `src/decoy/`. Update every import.
- README, `BUILD_PLAN.md`, `REPO_ARCHITECTURE_PLAN.md`, `CLAUDE.md`, `dev-help.md`: rename text references; update install instructions to `pip install decoy`.

### Deprecation shim
Ship one minor version with a `forge` console script that prints:
```
The `forge` CLI is now `decoy`. Install: pip install decoy. Docs: https://decoy.dev
```
…and then exits non-zero. Remove the shim in the version after.

### Examples and fixtures
- `examples/*.yaml`: any top-level `forge:` config keys rename to `decoy:`. Field/transform names inside YAML stay (`mask:`, `transform:`, etc.) — those are taxonomy terms, not brand.
- Test fixtures referencing `forge` in paths or output snapshots: regenerate.

### Engine dep
- `pyproject.toml` dependency `forge-engine` → `decoy-engine`. Coordinate the version bump so this CLI release lands *after* the engine release.
- Imports: `from forge_engine import …` → `from decoy_engine import …`.

## Sequencing

1. Wait for `decoy-engine` to publish.
2. Land rename in this repo on a branch.
3. Tag a release that includes both `decoy` and the deprecation `forge` shim.
4. One minor later, remove the shim.

## Verification

- `pip install -e .` from a clean venv.
- `decoy --help` returns help text branded "Decoy".
- `decoy run examples/mask_example.yaml` runs the existing fixture without error.
- `forge --help` (deprecation shim) prints the rename message and exits non-zero.
- `grep -ri "forge" src/ examples/ | grep -v "decoy_engine\|HIPAA"` returns zero hits other than the shim itself.
- `grep -ri "HIPPA" .` returns zero hits.
