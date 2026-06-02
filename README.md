# decoy

Free developer/CI CLI wrapper for Decoy.

`decoy` is production-usable for local YAML validation, local file runs,
local STORM scans, demos, templates, and fixtures. It is not the
paid self-hosted platform product: users, RBAC, API keys, schedules, triggers,
reviews, audit logs, Reporting, and evidence packages live in `decoy-platform`.

Start with the central documentation hub:

- [Documentation Hub](../decoy-platform/docs/README.md)
- [Master Roadmap](../decoy-platform/docs/ROADMAP.md)
- [CLI YAML And Workflow Guide](../decoy-platform/docs/guides/cli-yaml-workflows.md)
- [New Developer Onboarding](../decoy-platform/docs/guides/new-developer-onboarding.md) -- start here if you're new to the four-repo family
- [CLI legacy README](../decoy-platform/docs/backlog/v2/legacy-guides/cli-readme-legacy.md)
- [CLI UX Guide](../decoy-platform/docs/guides/cli-ux.md)

## Exit codes

Every `decoy` subcommand returns one of these four exit codes. Scripts, Make recipes, and CI pipelines can switch on the integer value (it is stable across releases).

| Code | Name                   | Meaning                                                                                    |
|------|------------------------|--------------------------------------------------------------------------------------------|
| 0    | EXIT_OK                | Success. The command did what it said.                                                     |
| 1    | EXIT_USAGE             | Usage error: config did not validate, path did not exist, flag combination was invalid.    |
| 2    | EXIT_DEPRECATED_SHIM   | The legacy `forge` console entry point was invoked; migrate to `decoy ...`.                |
| 3    | EXIT_RUNTIME           | The CLI itself failed mid-run (engine error, output write failure, transient I/O problem). |

Named constants live in `decoy.cli.exit_codes` for callers that import them in Python. Run `decoy explain exit-codes` for the same table from the CLI.

