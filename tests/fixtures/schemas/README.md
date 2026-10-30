# Vendored schemas (test oracles only)

`sarif-schema-2.1.0.json` is the OASIS SARIF 2.1.0 JSON Schema (JSON Schema Draft-04).
It is a test oracle for `decoy ci check --format sarif`; it is not shipped in the wheel and
no runtime SARIF library is used.

| Field | Value |
|---|---|
| Schema `id` (declared in the file) | `https://docs.oasis-open.org/sarif/sarif/v2.1.0/errata01/os/schemas/sarif-schema-2.1.0.json` |
| Retrieved from | `https://raw.githubusercontent.com/oasis-tcs/sarif-spec/main/sarif-2.1/schema/sarif-schema-2.1.0.json` (the OASIS SARIF TC's repository) |
| Retrieved on | 2026-10-29 |
| SHA-256 | `c3b4bb2d6093897483348925aaa73af03b3e3f4bd4ca38cef26dcb4212a2682e` |
| Oracle used by | `tests/ci_support.py::assert_valid_sarif` (`jsonschema.Draft4Validator`) |

Provenance caveat: `docs.oasis-open.org` was not reachable from the build environment, so the
file could not be byte-compared with the published Errata 01 artifact at that URL. The
declared `id` and `$schema` match Errata 01; a maintainer with access should confirm the hash
against the published file and record the result here.

Notice: the schema is OASIS work product (c) OASIS Open; it is vendored unmodified, for
validation only, under the OASIS TC's terms.
