# Pipeline Graph — `decoy` CLI

> **Status:** target — CLI passthrough for the cross-repo graph pipeline contract.
> **Last reviewed:** 2026-05-05
> **Canonical source:** [forge-platform/PIPELINE_GRAPH_GUIDE.md](../forge-platform/PIPELINE_GRAPH_GUIDE.md). When the contract changes, update the platform copy first; mirror here in the same PR.

This is the CLI-side mirror. For the cross-repo split, YAML schema, node-kinds catalog, per-node preview API, and phased rollout plan, **read the platform copy first** (link above) — it owns the contract.

CLI-specific notes are below; everything else is duplicated from the platform doc verbatim.

---

## CLI responsibilities

The CLI is a thin pass-through. It detects `mode: graph` in the YAML and dispatches to the engine's `run_graph` / `validate_graph` entry points.

| Command | Behavior on `mode: graph` |
|---|---|
| `decoy validate <yaml>` | Calls `decoy_engine.validate_graph(yaml_text)` and reports `OK` or the validation error |
| `decoy run <yaml>` | Calls `decoy_engine.run_graph(yaml_text, ctx)` and reports the run-summary card or the failed-node error |
| `decoy preview <yaml> <node_id>` | _(future)_ — calls `decoy_engine.preview_graph` |

Mode is read from the YAML, not the `--mode` flag. The flag remains as a back-compat hint for legacy pipelines that omit a top-level `mode:` key.

## Connector handling

The CLI has no platform connector store. `source.db` and `target.db` graph nodes must use inline `dsn:` strings:

```yaml
- id: src
  kind: source.db
  config:
    dsn: postgresql+psycopg2://user:pass@host/db
    schema: public
    table: customers
```

If a YAML uses `connector_id:` instead of `dsn:`, the CLI surfaces the engine's "ctx.resolve_connector is None" error — the user must edit the YAML to inline the DSN before running it from the CLI.

## Out of scope (this phase)

- A CLI-side connector store (deferred — the platform owns connectors).
- `decoy preview <yaml> <node_id>` command (deferred until a use case emerges).
- Streaming progress for long graph runs (current CLI shows a single spinner per command).
