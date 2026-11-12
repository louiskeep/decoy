# Trace export to your collector

Status: current

`decoy run` can send OpenTelemetry traces of a run to an OTLP/HTTP collector you operate.
Export is off unless you ask for it. This page lists what leaves the machine and the limits
you should know before you turn it on.

## Turn it on

Install the extra, then name the collector:

```
pip install decoy-cli[otel]
decoy run pipeline.yaml --otel-endpoint https://collector.example/v1/traces
```

`DECOY_OTEL_ENDPOINT` does the same without the flag. If the extra is missing, the flag exits
1 with `missing_extra`; the variable alone prints one warning and the run continues without
traces. Credentials go in `DECOY_OTEL_HEADERS` as `name=value,name=value`. There is no
headers flag, so a token never shows in the process list. Headers need an `https://`
endpoint, except for a loopback host (`localhost`, `127.0.0.0/8`, `::1`). A URL with
credentials, a query string or a fragment is refused with exit 1; the message names the
setting, never its value.

## What is exported

One trace per run. The root span is `decoy.run`. Under it sit the engine's phase spans, named
`decoy.phase.<phase>` (resolve, mask, publish and the other engine phases).

Span names, attribute keys and string values come from closed sets:

| Attribute | Value |
|---|---|
| `decoy.phase` | an engine phase name |
| `decoy.rows_in`, `decoy.rows_out`, `decoy.bytes` | counts |
| `decoy.elapsed_s` | seconds |
| `decoy.reason` | a registered reason code |
| `error.type` | an engine error class name, a builtin exception name, or the fallback `Exception`; only on a failed span |
| `decoy.outcome` | `success` or `failed` (root span) |
| `decoy.spans_dropped` | spans the run produced past the 256 cap (root span) |
| `decoy.engine.version` | the engine version (root span) |

`decoy.outcome` describes the pipeline run, not the process exit code. A run can export
`success` and still exit non-zero if a later step, such as writing evidence or enforcing
post-validation, fails.

The resource carries `service.name=decoy-cli` and the CLI version. Nothing else is sent: no
table, column or file name, no path, no connection string, no cell value, no error text. A
failed span has status ERROR with no description and no exception event.

## Standard `OTEL_*` variables are ignored

`OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS`, `OTEL_RESOURCE_ATTRIBUTES`,
certificate, compression and proxy variables have no effect. Only the Decoy settings above
choose the endpoint and the headers, so an organisation-wide token meant for another
collector is never sent to this one. Redirects are not followed, and only a 2xx reply counts
as delivered.

## Limits

- **Differential-privacy fits.** The `otel` extra adds five packages (the OpenTelemetry API,
  SDK, semantic conventions, proto and OTLP common packages). The engine's DP gate
  fingerprints every installed package and only the exact certified set passes, so with
  `decoy-cli[otel]` installed a DP fit (`decoy fit --epsilon`) refuses with
  `dp_stack_uncertified`. Run DP fits from an environment without the extra.
- **A dead collector loses spans, silently.** Export runs on a background thread with one
  attempt per batch and no retry. If the collector is down, slow or refuses the data, the
  spans are dropped, nothing is logged, and the run still passes. The exit code, the `--json`
  envelope and stderr do not change.
- **Exit can wait up to 2 seconds.** At the end of the run the CLI flushes for at most 2
  seconds, then exits. Spans still queued after that are lost.
- **Routes without phase spans.** The `--chunked` route (`run_mask_pipeline_chunked`) emits
  no engine phase events, so a chunked run exports the `decoy.run` root span only. Engine
  worker threads report to no recorder, so their phases are missing too. The `--rows`
  preview and the generate paths run through `run_pipeline` and export phase spans.
- **Trust.** Self-signed or internal-CA collectors are not supported: the exporter trusts the
  system certificate store only, and credential headers need `https`.
