# Agent Guide

Operating guide for coding agents working in the `decoy` CLI repo.

## Reading order

1. [README.md](README.md) for what the CLI is and how to install/run it.
2. [CODEMAP.md](CODEMAP.md) for the repository layout.
3. [CONTRIBUTING.md](CONTRIBUTING.md) for build/test/PR conventions.
4. [CLAUDE.md](CLAUDE.md) for agent-specific best-practice notes.

## Role split

The main session is the developer. Tech-lead reviews are handled by the `dennis` subagent (`~/.claude/agents/dennis.md`); delegate to him rather than performing reviews in the main session. Docs and code-hygiene passes go to the `barry` subagent (`~/.claude/agents/barry.md`).

## Scope of this repo

The CLI is a thin wrapper around `decoy-engine`. Data behavior belongs in the engine, not here. The CLI owns command surface, terminal UX, exit codes, packaged templates, and example configs.

---

Full agent-guide content lives in the commercial platform repo.
