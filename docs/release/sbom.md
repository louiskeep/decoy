# SBOM (CycloneDX)

**Status:** generator implemented (release readiness R1-c). The SBOM is not signed,
published or attached to any release; that wiring belongs to the release workflow.

`scripts/release/sbom.sh` writes a CycloneDX 1.6 JSON SBOM for the pinned third-party
runtime that the CLI bundle ships with.

```bash
scripts/release/sbom.sh                                   # requirements-certified.txt -> ./sbom.cdx.json
scripts/release/sbom.sh requirements-certified.txt out/sbom.cdx.json
```

Needs `uv` on PATH and network access to PyPI on the first run (the tools below run
through `uvx`; nothing is added to `pyproject.toml` or the locks).

## Which pin list

`requirements-certified.txt`, the only runtime-profile pin list in this repo: the exact
63-package third-party closure of the certified DP runtime, with no dev tooling.
`requirements-dev.lock` is the dev profile and the script refuses it. The bundle builder
(`packaging_tools/build_bundle.py`) installs wheels handed to it by the release pipeline
and reads no lock itself, so this file is the closest thing to a runtime lock.

Not in this SBOM: `decoy-engine`, `decoy-engine-native` and `decoy-cli` are the bundle's own
wheels, not third-party pins. The root component is `decoy-cli` (from `pyproject.toml`);
the engine's SBOM comes from `decoy-engine` (`scripts/release/sbom.sh uv.lock`).

## How it is built

The upstream `cyclonedx-py requirements` tool (`cyclonedx-bom==7.6.0` with
`cyclonedx-python-lib==11.12.0`, both pinned in the script) reads the pin list, writes the
SBOM and validates it against the CycloneDX schema. The format is never hand-written.

## What the output holds

- One component per pin: name, version and `pkg:pypi` purl. The pin list has no hashes, so
  components have none (a hashed pin list would carry them).
- No license for third-party components: the pin list carries none and the generator reads
  it only. The dependency graph is flat (the requirements input has no edges).
- Package names only: no paths, hostnames, environment values, timestamps or serial number.

## Reproducibility

`--output-reproducible` removes `serialNumber` and `metadata.timestamp`, and the script
unsets `SOURCE_DATE_EPOCH` so the environment cannot put a timestamp back. Same pin list and
same tool pins give byte-identical output.

## Refusals

The script exits non-zero and writes nothing when the pin list is missing or holds anything
but `name==version` pins, hashes and comments (index URLs, paths, git or direct URLs, `-r`/`-e`).

## Tests

`tests/unit/test_sbom_script.py`: schema validation, completeness against the pin list,
hashes, byte-identical reruns, leak canaries and the refusals above. It needs `uv`.
