# Security Policy

`decoy` is the CLI that drives `decoy-engine` for local validation, masking, generation, STORM, and FORECAST. The CLI runs in the user's shell with the user's privileges; there is no API surface and no auth boundary inside the CLI.

## Reporting a vulnerability

**Use GitHub Private Vulnerability Reporting:**

[https://github.com/louiskeep/decoy/security/advisories/new](https://github.com/louiskeep/decoy/security/advisories/new)

The report is private and visible only to repository maintainers. We will acknowledge receipt within 3 business days and aim to provide an initial assessment within 7 business days. Please do not file a public issue or contact support channels for security disclosures.

Include as much detail as you can:

- The affected version(s) of `decoy`.
- Steps to reproduce, or proof-of-concept code.
- The impact you believe the issue has.
- Any mitigations or workarounds you are aware of.

## Coordinated disclosure

We follow a 90-day coordinated-disclosure window from the date of initial report. We will work with you on a public-disclosure timeline that gives users a reasonable opportunity to update.

If a critical issue is being actively exploited, we may shorten this window.

## Supported versions

Only the most recent minor release of `decoy` receives security fixes. Older versions are not patched.

## Local secret-handling guidance

- Prefer `DECOY_MASTER_KEY` environment variable over passing `--master-key` on the command line. Shell history and process lists can leak command-line secrets.
- `decoy demo` and `decoy storm` write JSON output that can contain top values, sample sentinels, and detector metadata. These are fine to keep locally but may be sensitive to share; review scan JSON before posting.
- Custom Faker provider files load at process start with the current user's privileges. Treat the providers directory the same way you would treat any directory of executable Python.

## Security posture summary

`decoy` runs locally in the user's shell with the user's privileges. There is no server, no inbound network surface, and no telemetry phone-home. The engine library it calls is also local-only.

- **Input data and output data stay local** to the machine running the CLI. The CLI does not transmit data anywhere.
- **Determinism keys.** Decoy has two independent keying mechanisms; key derivation uses HKDF-SHA256 in both. (1) Keyed *masking* strategies (hash, format-preserving encryption, and other value-sensitive masks) are keyed off a *mask secret*, configured via `--mask-secret env:NAME` or the pipeline YAML's `global_settings.mask_secret_ref`. (2) Portable deterministic *synthetic generation* (generate_columns:) is keyed off a *master key*, via `--master-key` / `--key-label`; prefer the `DECOY_MASTER_KEY` environment variable over the flag. The two secrets are separate and neither affects the other. See `decoy explain keys`.
- **Custom providers.** Files passed via `--providers` load at startup and run with the user's privileges. Treat the providers directory the same way you would treat any directory of executable Python.
- **Pre-1.0 caveat.** The CLI is at version 0.1.0. Exit codes are stable (`decoy explain exit-codes`); other surfaces may change before 1.0.0 ships.
