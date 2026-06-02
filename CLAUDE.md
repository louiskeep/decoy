# Claude Guide

CLI-specific guidance for Claude and other coding agents working in this repo.

Use [CODEMAP.md](CODEMAP.md) for repo navigation before broad searches. Use [CONTRIBUTING.md](CONTRIBUTING.md) for the contributor entrypoint.

## Engineering best practices

The CLI is a thin Typer/Rich wrapper around `decoy-engine`. The rules that matter most here are about boundaries and discipline:

- Library code does not know its callers. The CLI's single-file graph-builder helper lives in this repo, not in the engine. The engine stays narrow.
- Pre-GA = hard delete. Pre-V2.1 CLI users are the dev team; breaking changes do not need migration adapters.
- Comments explain why, not what. CLI command handlers are short; comments only when a flag or default has a non-obvious reason.

## Core rule for non-trivial domain work

Use established methodology. For crypto, FK preservation, synth strategies, and other non-trivial primitives: survey how established tools or standards approach the problem before designing, and cite the source pattern in the implementing module's docstring. The CLI itself rarely owns this code (it lives in the engine), but the rule applies to anything CLI-side that touches data semantics.

---

Full engineering-best-practices and CLI-agent-guide documents live in the commercial platform repo.
