"""The post-scan report a `decoy run` writes, and what run and `report integrity` say about it.

SCAN-ML plan 4.7 (slice C2a). With `post_scan.integrity` on, `decoy run` writes the engine's
value-free report beside the outputs (`<first target dir>/<config stem>.post-scan.json`, or
`--integrity-out`), stamped with `config_sha256`: the SHA-256 of the YAML bytes the run read,
the identity IW 4.5 matches a report to its config by. The report is a run artifact like the
outputs, so it is written through `_atomic.write_local_target` in replace mode (write a temp,
then rename over the target: the POSIX atomic-replace idiom) and a rerun replaces it.

Here too: the `load_detectors` preflight that refuses a model before any source row is read,
the `--chunked` refusal of a model post-scan (the engine's own `post_scan_model_setting` rule
and `PostScanRouteError`, so the CLI keeps no copy of the rule), the post-scan card line and
`--json` block, and the blocked-run body of run's error handler. Everything printed is names,
ids, versions, counts and paths; a finding's text and the report body never reach the terminal.

Pattern: content-addressed identity of an input by its exact bytes, as pip's `--require-hashes`
and Git do; detector provenance on every finding, as Google Cloud DLP and AWS Macie report it.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import typer

from decoy._atomic import AtomicWriteError, WriteMode, describe, write_local_target
from decoy._config_file import ConfigFileError, load_pipeline, read_config_bytes
from decoy.cli.exit_codes import EXIT_USAGE
from decoy.cli.io._layout import RunLayout, shown_path
from decoy.cli.io._run_outputs import implicit_report_path
from decoy.ui.output import OutputMode, OutputState, emit_error
from decoy.ui.theme import warn

INTEGRITY_WRITE_FAILED = "run.integrity_write_failed"
_BLOCKED_FALLBACK = "The post-scan integrity check blocked the run."
_COUNTS = ("pass", "warning", "fail", "error")

INTEGRITY_OUT_OPTION: Any = typer.Option(
    None,
    "--integrity-out",
    help=(
        "Write the post-scan integrity report (post_scan.integrity: true) to this path, "
        "replacing any file there. Default: <first target's folder>/<config stem>.post-scan.json. "
        "Written for a blocked run too."
    ),
)


def config_sha256(data: bytes) -> str:
    """The `config_sha256` of a config: the hex SHA-256 of the exact bytes read."""
    return hashlib.sha256(data).hexdigest()


def _post_scan(config: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """The validated `post_scan` block when it asks for the integrity suite, else None."""
    from decoy_engine.config import post_scan_integrity_requested

    return config["post_scan"] if post_scan_integrity_requested(config) else None


def _unavailable(exc: Any, ner_model: str) -> Any:
    """The `ModelStatus` a `ModelUnavailableError` stands for, so the gate's one fix line names
    its hint."""
    from decoy_engine import ModelStatus, classifier_status, reasons

    if exc.code == reasons.provider.CLASSIFIER_UNAVAILABLE:
        model = classifier_status().model_id
        return ModelStatus("classifier", model, False, None, None, exc.reason, exc.cause_class)
    return ModelStatus("ner", ner_model, False, None, None, exc.reason, exc.cause_class)


def load_detector_set(detectors: Any, ner_model: str) -> tuple[Any, Any]:
    """`load_detectors` for a chosen set: (detector set, None) or (None, the status of the model
    that cannot run). The refusal is returned, not raised, so no chain reaches the caller."""
    from decoy_engine import ModelUnavailableError, load_detectors

    try:
        return load_detectors(tuple(detectors), ner_model=ner_model), None
    except ModelUnavailableError as exc:
        return None, _unavailable(exc, ner_model)


def _load(post: Mapping[str, Any]) -> tuple[Any, Any]:
    """`load_detector_set` for a post-scan block."""
    from decoy_engine.detection.ner import DEFAULT_NER_MODEL

    return load_detector_set(
        post.get("detectors") or ("regex",), post.get("ner_model") or DEFAULT_NER_MODEL
    )


def preflight_detectors(config: Mapping[str, Any]) -> None:
    """Load the post-scan models before any source is read (plan 4.1 matrix); the engine run
    reuses the loaded set from its per-process cache. A model that cannot load refuses through
    the gate's own finding: exit 1, the reason code and the fix."""
    post = _post_scan(config)
    if post is None:
        return
    _, refused = _load(post)
    if refused is not None:
        from decoy.cli.gate import PreRunCheckError, model_finding

        raise PreRunCheckError.from_findings([model_finding(refused)])


def refuse_unchecked_chunked(config: Mapping[str, Any]) -> None:
    """`--chunked` runs no post-scan: refuse a model ask with the engine's route refusal."""
    from decoy_engine import PostScanRouteError
    from decoy_engine.config import post_scan_model_setting

    setting = post_scan_model_setting(config)
    if setting is not None:
        raise PostScanRouteError("chunked", setting)


def report_file(
    given: Path | None, layout: RunLayout | None, config: Mapping[str, Any], config_path: Path
) -> Path | None:
    """Where this run's report goes: `--integrity-out`, else beside the first target."""
    if given is not None:
        return given
    first = next(iter((config.get("targets") or {}).values()), None)
    raw = first.get("path") if isinstance(first, Mapping) else None
    if layout is None or not isinstance(raw, str):
        return None
    return implicit_report_path(layout.place_target(raw), config_path)


def run_report(config: Mapping[str, Any], metrics: Mapping[str, Any]) -> dict | None:
    """The report a finished run writes: only when the config asked for the integrity suite."""
    from decoy_engine.verification.postmask import SCHEMA_VERSION

    if _post_scan(config) is None:
        return None
    # The engine exports no name for the metrics key, so the report is found by its own tag.
    reports = (m for m in metrics.values() if isinstance(m, Mapping))
    return next((dict(m) for m in reports if m.get("schema_version") == SCHEMA_VERSION), None)


def _write(path: Path, report: Mapping[str, Any], sha: str | None) -> str | None:
    """Write the stamped report; the failure text (code and path) when it cannot be written."""
    data = json.dumps({**report, "config_sha256": sha}, indent=2).encode("utf-8")
    try:
        # As the target writer does: a blocked run never made the first target's folder.
        path.parent.mkdir(parents=True, exist_ok=True)
        write_local_target(path, data, WriteMode.REPLACE)
    except OSError as exc:
        return f"could not write the post-scan report {path}: {type(exc).__name__}"
    except AtomicWriteError as exc:
        return f"could not write the post-scan report {path}: {describe(exc)}"
    return None


def write_run_report(
    report: Mapping[str, Any] | None, path: Path | None, sha: str | None
) -> str | None:
    """Write a finished run's report after its outputs; the failure text when it cannot be
    written. It never ends the run: `run/_flow.py` raises the typed refusal (exit 3)."""
    if report is None or path is None:
        return None
    return _write(path, report, sha)


def _detectors(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    out = []
    for run in report.get("detectors") or ():
        model = run.get("model") or {}
        out.append(
            {
                "source": run.get("source"),
                "model_id": model.get("id"),
                "model_version": model.get("version"),
            }
        )
    return out


def post_scan_members(report: Mapping[str, Any] | None, path: Path | None) -> dict[str, Any]:
    """The run `--json` `post_scan` member: detectors, severity counts and the report path."""
    if report is None:
        return {}
    counts = {k: int(report.get(f"{k}_count") or 0) for k in _COUNTS}
    where = str(path.resolve()) if path is not None else None
    return {"post_scan": {"detectors": _detectors(report), "counts": counts, "report": where}}


def post_scan_line(report: Mapping[str, Any], path: Path | None) -> str:
    """`Post-scan: regex; ner en_core_web_sm 3.8.0. 2 warnings, 0 fail. Report: <path>`."""
    names = [
        " ".join(str(p) for p in (d["source"], d["model_id"], d["model_version"]) if p)
        for d in _detectors(report)
    ]
    warnings = int(report.get("warning_count") or 0)
    fails = int(report.get("fail_count") or 0)
    plural = "" if warnings == 1 else "s"
    where = shown_path(path.resolve()) if path is not None else "not written"
    return (
        f"Post-scan: {'; '.join(names)}. {warnings} warning{plural}, {fails} fail. Report: {where}"
    )


def print_post_scan(
    state: OutputState, report: Mapping[str, Any] | None, path: Path | None
) -> None:
    """The run card's post-scan line, in the default output mode only."""
    if report is not None and state.mode is OutputMode.default:
        state.console.print(post_scan_line(report, path), markup=False, soft_wrap=True)


def blocked_run(
    state: OutputState, exc: Any, path: Path | None, sha: str | None
) -> tuple[str, dict[str, Any]]:
    """The blocked-run branch of run's error handler (plan 4.7): write the report the error
    carries, print the post-scan line, and return the fixed safe summary and the `--json`
    members. `str(exc)` is never used: the text is the reason registry's summary."""
    from decoy_engine import reasons

    namespace, _, code = str(getattr(exc, "reason", "")).partition(".")
    known = bool(code) and reasons.find(namespace, code) is not None
    summary = reasons.get(namespace, code).summary if known else _BLOCKED_FALLBACK
    report = dict(getattr(exc, "report", None) or {})
    failed = _write(path, report, sha) if path is not None else "no report path"
    written = path if failed is None else None
    if state.mode is not OutputMode.json and state.mode is not OutputMode.quiet:
        state.err_console.print(post_scan_line(report, written), markup=False)
        if failed is not None:
            state.err_console.print(
                warn("warning:"), f"{INTEGRITY_WRITE_FAILED}: {failed}", markup=False
            )
    members: dict[str, Any] = {"error_kind": "post_scan_blocked"}
    if known:
        members["code"] = f"{namespace}.{code}"
    return summary, {**members, **post_scan_members(report, written)}


# --- `decoy report integrity --config` --------------------------------------------------------


def read_report_config(path: Path) -> tuple[dict[str, Any], str]:
    """The config mapping and its `config_sha256`, from one read of its bytes."""
    data = read_config_bytes(path)
    pipeline = load_pipeline(path, text=data)
    if pipeline.unreviewed:
        raise ConfigFileError.from_problems(pipeline.unreviewed)
    return pipeline.config, config_sha256(data)


def bare_report_config() -> dict[str, Any]:
    """The minimal config `report integrity` checks with when no `--config` is given."""
    return {
        "version": 2,
        "global_settings": {"seed": 0},
        "sources": {},
        "tables": [],
        "targets": {},
        "relationships": [],
    }


def report_detectors(
    state: OutputState, config: Mapping[str, Any], context: Mapping[str, str]
) -> Any:
    """The config's post-scan detector set for `report integrity`, loaded before either CSV is
    read; None (regex only, today's report) when it asks for no model. A model that cannot run
    exits 1 with its reason code and the fix."""
    post = config.get("post_scan") or {}
    if all(source == "regex" for source in post.get("detectors") or ()):
        return None
    detectors, refused = _load(post)
    if refused is not None:
        from decoy.cli.models import hint

        text = f"the {refused.source} model {refused.model_id} cannot run here."
        emit_error(
            state,
            "report integrity",
            text,
            code=refused.reason,
            hint=hint(refused),
            context=context,
        )
        raise typer.Exit(code=EXIT_USAGE)
    return detectors


__all__ = [
    "INTEGRITY_OUT_OPTION",
    "INTEGRITY_WRITE_FAILED",
    "bare_report_config",
    "blocked_run",
    "config_sha256",
    "load_detector_set",
    "post_scan_line",
    "post_scan_members",
    "preflight_detectors",
    "print_post_scan",
    "read_report_config",
    "refuse_unchecked_chunked",
    "report_detectors",
    "report_file",
    "run_report",
    "write_run_report",
]
