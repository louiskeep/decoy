# Claude Guide

CLI Claude guidance moved to [../decoy-platform/docs/guides/cli-claude-guide.md](../decoy-platform/docs/guides/cli-claude-guide.md).

Use [../decoy-platform/docs/README.md](../decoy-platform/docs/README.md) as the documentation entrypoint.

## Engineering best practices

Before writing or reviewing non-trivial CLI code, consult [../decoy-platform/docs/guides/engineering-best-practices.md](../decoy-platform/docs/guides/engineering-best-practices.md). The CLI is a thin wrapper around `decoy-engine`; the rules that matter most here are about boundaries and discipline:

- §3.3 Library code doesn't know its callers. The CLI's single-file graph-builder helper (V2.1) lives in this repo, not in the engine. The engine stays narrow.
- §8.1 Pre-GA = hard delete. Pre-V2.1 CLI users are the dev team; breaking changes don't need migration adapters.
- §10.1 Comments explain why, not what. CLI command handlers are short; comments only when a flag or default has a non-obvious reason.
