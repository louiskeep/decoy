"""The value-free result boundary and the `decoy-ci/v1` manifest model.

Every emitter (JSON, SARIF, Markdown, stderr) consumes ONLY `SafeCiReport`, and the only
way to put a finding into one is `SafeFinding.create`, which accepts tokens and numbers but
no free text, no exception, no message, and no sample. The prose a report shows is looked
up from fixed authored registries here, so a leaked value has no path to an output byte.

Prior art: SARIF 2.1.0 (OASIS) `result`/`partialFingerprints` semantics for the fingerprint
and region rules; GitHub code scanning's use of stable `ruleId` + fingerprints for alert
identity; Pydantic v2 strict models for the manifest (SDV-style typed config, no custom
parser); the existing `decoy.cli.exit_codes` taxonomy for the exit integers.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    StringConstraints,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

from decoy.ci import CI_MANIFEST_VERSION, CI_REPORT_VERSION
from decoy.cli.exit_codes import (
    EXIT_CAPACITY,
    EXIT_FINDINGS,
    EXIT_OK,
    EXIT_RUNTIME,
    EXIT_USAGE,
    EXIT_WARNINGS,
)

__all__ = [
    "CI_MANIFEST_VERSION",
    "CI_REPORT_VERSION",
    "NOTE_TEXTS",
    "REASON_CODES",
    "SAFE_MESSAGES",
    "CheckOutcome",
    "CheckResult",
    "CiManifest",
    "SafeCiReport",
    "SafeFinding",
    "SourceLocation",
    "UnsafeFindingError",
]

# ---------------------------------------------------------------------------
# Fixed authored registries (the ONLY prose a report can carry)
# ---------------------------------------------------------------------------

SAFE_MESSAGES: dict[str, str] = {
    "ci.validation_failed": "Selected validation rule failed",
    "ci.validation_warning": "Selected validation rule raised a warning",
    "ci.drift_pii_bucket_increased": "A field's PII bucket increased against the saved baseline",
    "ci.drift_new_high_pii_field": "A new high-PII field appeared against the saved baseline",
    "ci.drift_new_quasi_identifier_group": (
        "A new quasi-identifier group appeared against the saved baseline"
    ),
    "ci.evidence_mismatch": "Evidence manifest does not match the current files",
    "ci.staged_pattern_match": "Configured sensitive pattern matched staged content",
}

NOTE_TEXTS: dict[str, str] = {
    "ci.precommit_mode_narrowed": (
        "Running in pre-commit mode; validation narrowed from 'full' to 'config' and only "
        "validation plus the staged scan ran (no source or preflight reads)."
    ),
}

REASON_CODES: frozenset[str] = frozenset(
    {
        "ci.manifest_unreadable",
        "ci.manifest_invalid",
        "ci.manifest_version_unsupported",
        "ci.manifest_path_rejected",
        "ci.input_missing",
        "ci.evidence_unreadable",
        "ci.drift_unreadable",
        "ci.regression_runner_unavailable",
        "ci.no_staged_files",
        "ci.staged_scan_limit",
        "ci.staged_unsupported_entry",
        "ci.staged_unmerged",
        "ci.git_failure",
        "ci.check_runtime_failure",
        "ci.capacity_refused",
        "ci.precommit_not_applicable",
    }
)

CHECK_KINDS: frozenset[str] = frozenset(
    {"validation", "drift", "evidence", "regression", "staged_scan", "manifest"}
)
CHECK_STATUSES: frozenset[str] = frozenset(
    {"ok", "noop", "findings", "partial", "refused", "failed"}
)
LEVELS: frozenset[str] = frozenset({"error", "warning", "note"})
EXIT_CODES: frozenset[int] = frozenset(
    {EXIT_OK, EXIT_USAGE, EXIT_WARNINGS, EXIT_RUNTIME, EXIT_FINDINGS, EXIT_CAPACITY}
)
# Highest precedence first: capacity > runtime > invalid/refused > findings > warnings > ok.
EXIT_PRECEDENCE: tuple[int, ...] = (
    EXIT_CAPACITY,
    EXIT_RUNTIME,
    EXIT_USAGE,
    EXIT_FINDINGS,
    EXIT_WARNINGS,
    EXIT_OK,
)

_TOKEN = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class UnsafeFindingError(ValueError):
    """A finding or location was refused at the value-free boundary.

    Messages are fixed strings; they never echo the offending input.
    """


def _token(value: object, what: str) -> str:
    if not isinstance(value, str) or not _TOKEN.match(value):
        raise UnsafeFindingError(f"{what} is not a bounded token")
    return value


def _pos_int(value: object, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise UnsafeFindingError(f"{what} must be a positive one-based integer")
    return value


# ---------------------------------------------------------------------------
# Location
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceLocation:
    """A repository-relative file and an optional one-based region.

    `uri` holds the DECODED POSIX path (so Git paths with odd bytes round-trip); output
    surfaces percent-encode it via `encoded_uri`. A region needs start line and column;
    end line/column are optional and the end column is exclusive (SARIF 2.1.0 3.30).
    """

    uri: str
    start_line: int | None = None
    start_column: int | None = None
    end_line: int | None = None
    end_column: int | None = None

    def __post_init__(self) -> None:
        uri = self.uri
        if not isinstance(uri, str) or not uri or "\x00" in uri:
            raise UnsafeFindingError("location uri is not a repository-relative path")
        if (
            uri.startswith("/")
            or "\\" in uri
            or "://" in uri
            or re.match(r"^[A-Za-z]:", uri)
            or any(seg in ("", "..", ".") for seg in uri.split("/"))
        ):
            raise UnsafeFindingError("location uri is not a repository-relative path")
        s_line, s_col, e_line, e_col = (
            self.start_line,
            self.start_column,
            self.end_line,
            self.end_column,
        )
        if s_line is None and s_col is None and e_line is None and e_col is None:
            return
        if s_line is None or s_col is None:
            raise UnsafeFindingError("a region needs a start line and a start column")
        _pos_int(s_line, "start line")
        _pos_int(s_col, "start column")
        if (e_line is None) != (e_col is None):
            raise UnsafeFindingError("end line and end column go together")
        if e_line is not None:
            _pos_int(e_line, "end line")
            _pos_int(e_col, "end column")
            assert e_col is not None
            if e_line < s_line or (e_line == s_line and e_col <= s_col):
                raise UnsafeFindingError("region end must follow its start")

    @property
    def has_region(self) -> bool:
        return self.start_line is not None

    @property
    def encoded_uri(self) -> str:
        from urllib.parse import quote

        # bytes + surrogateescape: a non-UTF-8 Git path still encodes losslessly
        return quote(self.uri.encode("utf-8", "surrogateescape"), safe="/")

    def sort_key(self) -> tuple[str, int, int]:
        return (self.uri, self.start_line or 0, self.start_column or 0)


# ---------------------------------------------------------------------------
# Finding / check / report
# ---------------------------------------------------------------------------


def _fingerprint(rule_id: str, path: str | None, logical_path: str | None) -> str:
    # Value-free by construction: tokens and paths only, never a scalar or a line number,
    # so a code-scanning alert tracks across line moves instead of churning.
    payload = "\x1f".join((rule_id, path or "", logical_path or ""))
    return hashlib.sha256(payload.encode("utf-8", "surrogateescape")).hexdigest()


@dataclass(frozen=True)
class SafeFinding:
    rule_id: str
    level: str
    safe_message_id: str
    check_id: str
    location: SourceLocation | None
    fingerprint: str
    occurrences: int = 1

    def __post_init__(self) -> None:
        _token(self.rule_id, "rule id")
        _token(self.check_id, "check id")
        if self.level not in LEVELS:
            raise UnsafeFindingError("level is not recognised")
        if self.safe_message_id not in SAFE_MESSAGES:
            raise UnsafeFindingError("safe message id is not in the registry")
        if self.location is not None and not isinstance(self.location, SourceLocation):
            raise UnsafeFindingError("location must be a SourceLocation")
        if not isinstance(self.fingerprint, str) or not _HEX64.match(self.fingerprint):
            raise UnsafeFindingError("fingerprint is not a sha256 hex digest")
        _pos_int(self.occurrences, "occurrences")

    def validate(self) -> None:
        self.__post_init__()

    @classmethod
    def create(
        cls,
        *,
        rule_id: str,
        level: str,
        safe_message_id: str,
        check_id: str,
        location: SourceLocation | None = None,
        logical_path: str | None = None,
        artifact_path: str | None = None,
        occurrences: int = 1,
    ) -> SafeFinding:
        """The choke point. No message, detail, sample, or exception parameter exists."""
        _token(rule_id, "rule id")
        path = artifact_path if artifact_path is not None else (location.uri if location else None)
        return cls(
            rule_id=rule_id,
            level=level,
            safe_message_id=safe_message_id,
            check_id=check_id,
            location=location,
            fingerprint=_fingerprint(rule_id, path, logical_path),
            occurrences=occurrences,
        )

    @property
    def message(self) -> str:
        return SAFE_MESSAGES[self.safe_message_id]

    def sort_key(self) -> tuple:
        loc = self.location.sort_key() if self.location else ("", 0, 0)
        return (self.check_id, self.rule_id, *loc, self.level, self.fingerprint)


def _plain_int(value: object) -> bool:
    return type(value) is int


@dataclass(frozen=True)
class CheckResult:
    id: str
    kind: str
    status: str
    reason_code: str | None
    finding_count: int

    def __post_init__(self) -> None:
        _token(self.id, "check id")
        if self.kind not in CHECK_KINDS:
            raise UnsafeFindingError("check kind is not recognised")
        if self.status not in CHECK_STATUSES:
            raise UnsafeFindingError("check status is not recognised")
        if self.reason_code is not None and self.reason_code not in REASON_CODES:
            raise UnsafeFindingError("reason code is not in the registry")
        if not _plain_int(self.finding_count) or self.finding_count < 0:
            raise UnsafeFindingError("finding count must be a non-negative integer")

    def validate(self) -> None:
        self.__post_init__()


@dataclass(frozen=True)
class CheckOutcome:
    result: CheckResult
    findings: tuple[SafeFinding, ...]
    exit_code: int

    def __post_init__(self) -> None:
        if not isinstance(self.result, CheckResult):
            raise UnsafeFindingError("result must be a CheckResult")
        self.result.validate()
        _validate_findings(self.findings)
        if not _plain_int(self.exit_code) or self.exit_code not in EXIT_CODES:
            raise UnsafeFindingError("exit code is not in the public taxonomy")
        if self.result.finding_count != len(self.findings):
            raise UnsafeFindingError("finding count does not match the findings")
        if self.result.status in ("partial", "refused", "failed") and self.exit_code == EXIT_OK:
            raise UnsafeFindingError("an incomplete check cannot exit 0")

    @classmethod
    def create(
        cls,
        *,
        id: str,
        kind: str,
        status: str,
        reason_code: str | None,
        findings: Iterable[SafeFinding] = (),
        exit_code: int,
    ) -> CheckOutcome:
        _token(id, "check id")
        if kind not in CHECK_KINDS:
            raise ValueError("unknown check kind")
        if status not in CHECK_STATUSES:
            raise ValueError("unknown check status")
        if reason_code is not None and reason_code not in REASON_CODES:
            raise ValueError("unknown reason code")
        if exit_code not in EXIT_CODES:
            raise ValueError("exit code is not in the public taxonomy")
        if status in ("partial", "refused", "failed") and exit_code == EXIT_OK:
            raise ValueError("an incomplete check cannot exit 0")
        # Deduplicated and ordered here so finding_count always equals what is emitted.
        items = tuple(sorted(set(findings), key=SafeFinding.sort_key))
        return cls(CheckResult(id, kind, status, reason_code, len(items)), items, exit_code)


_COMPLETED = frozenset({"ok", "noop", "findings"})
REPORT_STATUSES: frozenset[str] = CHECK_STATUSES - {"failed"}


def _validate_findings(findings: object) -> None:
    if not isinstance(findings, tuple):
        raise UnsafeFindingError("findings must be a tuple of SafeFinding")
    for finding in findings:
        if not isinstance(finding, SafeFinding):
            raise UnsafeFindingError("findings must be a tuple of SafeFinding")
        finding.validate()


@dataclass(frozen=True)
class SafeCiReport:
    schema_version: str
    status: str
    exit_code: int
    checks: tuple[CheckResult, ...]
    notes: tuple[str, ...]
    findings: tuple[SafeFinding, ...]

    def __post_init__(self) -> None:
        # The factories are conveniences; this is the gate. Every string a renderer can emit
        # is either a registry key or a bounded token, so free text has no field to ride in.
        if self.schema_version != CI_REPORT_VERSION:
            raise UnsafeFindingError("report schema version is not recognised")
        if self.status not in REPORT_STATUSES:
            raise UnsafeFindingError("report status is not recognised")
        if not _plain_int(self.exit_code) or self.exit_code not in EXIT_CODES:
            raise UnsafeFindingError("exit code is not in the public taxonomy")
        if not isinstance(self.checks, tuple) or not self.checks:
            raise UnsafeFindingError("a report needs a tuple of checks")
        for check in self.checks:
            if not isinstance(check, CheckResult):
                raise UnsafeFindingError("checks must be CheckResult values")
            check.validate()
        if not isinstance(self.notes, tuple) or any(
            not isinstance(n, str) or n not in NOTE_TEXTS for n in self.notes
        ):
            raise UnsafeFindingError("notes must be registered note ids")
        _validate_findings(self.findings)

    def validate(self) -> None:
        """Re-run the gate; emitters call it so a post-construction mutation cannot slip by."""
        self.__post_init__()

    @classmethod
    def from_outcomes(
        cls, outcomes: Sequence[CheckOutcome], notes: Iterable[str] = ()
    ) -> SafeCiReport:
        if not outcomes:
            raise ValueError("a report needs at least one check")
        note_ids = tuple(dict.fromkeys(notes))
        if any(n not in NOTE_TEXTS for n in note_ids):
            raise ValueError("unknown note id")
        present = {o.exit_code for o in outcomes}
        exit_code = next(code for code in EXIT_PRECEDENCE if code in present)
        statuses = [o.result.status for o in outcomes]
        completed = any(s in _COMPLETED for s in statuses)
        if "partial" in statuses:
            status = "partial"
        elif "refused" in statuses or "failed" in statuses:
            # `refused` is reserved for the case where nothing could run at all; a lone
            # runtime failure is incomplete coverage, so it is `partial` (and exits 3).
            status = "partial" if completed or "failed" in statuses else "refused"
        elif "findings" in statuses:
            status = "findings"
        elif all(s == "noop" for s in statuses):
            status = "noop"
        else:
            status = "ok"
        unique = sorted(
            {f for o in outcomes for f in o.findings},
            key=SafeFinding.sort_key,
        )
        return cls(
            CI_REPORT_VERSION,
            status,
            exit_code,
            tuple(o.result for o in outcomes),
            note_ids,
            tuple(unique),
        )


# ---------------------------------------------------------------------------
# Manifest model (decoy-ci/v1)
# ---------------------------------------------------------------------------

MAX_PIPELINES = 32
MAX_DRIFT = 32
MAX_EVIDENCE = 32
MAX_REGRESSION = 16
MAX_PATTERNS = 32
LITERAL_MIN_BYTES = 4
LITERAL_MAX_BYTES = 128

# Hard maxima; a manifest may lower these, never raise them.
HARD_MAX_FILES = 200
HARD_MAX_BLOB_BYTES = 1024 * 1024
HARD_MAX_TOTAL_BYTES = 5 * 1024 * 1024
HARD_MAX_FINDING_GROUPS = 100
HARD_MAX_GIT_SECONDS = 10

Id = Annotated[StrictStr, StringConstraints(pattern=r"^[a-z][a-z0-9_.-]{0,63}$")]


def _check_repo_path(value: str) -> str:
    bad = (
        not value
        or "\x00" in value
        or "\\" in value
        or value.startswith("/")
        or re.match(r"^[A-Za-z]:", value)
        or any(seg == ".." for seg in value.split("/"))
    )
    if bad:
        raise PydanticCustomError("path_rejected", "path is not a safe repository-relative path")
    return value


RepoPath = Annotated[StrictStr, Field(max_length=1024)]

_GLOB_CHARS = re.compile(r"^[^\x00-\x1f\\\[\]{}!]+$")


def _check_glob(value: str) -> str:
    if (
        not value
        or value.startswith("/")
        or not _GLOB_CHARS.match(value)
        or any(seg == ".." for seg in value.split("/"))
        or re.match(r"^[A-Za-z]:", value)
    ):
        raise PydanticCustomError("invalid_glob", "glob is not supported")
    return value


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PipelineRef(_Strict):
    """A pipeline YAML file validated by the validation check (repo-relative to the manifest)."""

    id: Id
    path: RepoPath

    check_path = field_validator("path")(_check_repo_path)


class ValidationCheck(_Strict):
    """Existing `decoy validate` semantics: `full` = config+compile+preflight, `config` = config layer only."""

    enabled: StrictBool = True
    mode: Literal["full", "config"] = "full"
    pipelines: tuple[Id, ...] | None = Field(default=None, min_length=1, max_length=MAX_PIPELINES)
    fail_on_warning: StrictBool = True


class DriftCheck(_Strict):
    """Compare two saved STORM scan JSON files with the `scan diff` categorizer."""

    id: Id
    baseline: RepoPath
    current: RepoPath
    blocking: StrictBool = True

    check_paths = field_validator("baseline", "current")(_check_repo_path)


class EvidenceCheck(_Strict):
    """Verify a cli-local-1 evidence manifest with the `report verify` fingerprint check."""

    id: Id
    manifest: RepoPath

    check_path = field_validator("manifest")(_check_repo_path)


class RegressionRef(_Strict):
    """Reference to an F12 regression suite. Refused until a public F12 runner exists."""

    id: Id
    suite: RepoPath

    check_path = field_validator("suite")(_check_repo_path)


class Checks(_Strict):
    """Selected checks. Omitted `checks` means full validation of every pipeline."""

    validation: ValidationCheck = ValidationCheck()
    drift: tuple[DriftCheck, ...] = Field(default=(), max_length=MAX_DRIFT)
    evidence: tuple[EvidenceCheck, ...] = Field(default=(), max_length=MAX_EVIDENCE)
    regression_suites: tuple[RegressionRef, ...] = Field(default=(), max_length=MAX_REGRESSION)


Glob = Annotated[StrictStr, Field(max_length=512)]


class StagedPattern(_Strict):
    """An exact UTF-8 byte literal (4-128 bytes) scanned for in staged blobs of matching paths."""

    id: Id
    literal: StrictStr
    paths: tuple[Glob, ...] = Field(min_length=1, max_length=32)
    exclude_paths: tuple[Glob, ...] = Field(default=(), max_length=32)

    @field_validator("literal")
    @classmethod
    def _literal(cls, value: str) -> str:
        try:
            size = len(value.encode("utf-8"))
        except UnicodeEncodeError as exc:
            raise PydanticCustomError("invalid_literal", "literal is not valid UTF-8") from exc
        if not LITERAL_MIN_BYTES <= size <= LITERAL_MAX_BYTES:
            raise PydanticCustomError("invalid_literal", "literal size is out of bounds")
        if any((ord(c) < 0x20 and c != "\t") or ord(c) == 0x7F for c in value):
            raise PydanticCustomError("invalid_literal", "literal has control characters")
        return value

    @field_validator("paths", "exclude_paths")
    @classmethod
    def _globs(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_check_glob(v) for v in values)


class StagedLimits(_Strict):
    """Scan limits. Each default is also the hard maximum: a manifest may lower, never raise."""

    max_files: StrictInt = Field(default=HARD_MAX_FILES, ge=1, le=HARD_MAX_FILES)
    max_blob_bytes: StrictInt = Field(default=HARD_MAX_BLOB_BYTES, ge=1, le=HARD_MAX_BLOB_BYTES)
    max_total_bytes: StrictInt = Field(default=HARD_MAX_TOTAL_BYTES, ge=1, le=HARD_MAX_TOTAL_BYTES)
    max_finding_groups: StrictInt = Field(
        default=HARD_MAX_FINDING_GROUPS, ge=1, le=HARD_MAX_FINDING_GROUPS
    )
    max_git_seconds: StrictInt = Field(default=HARD_MAX_GIT_SECONDS, ge=1, le=HARD_MAX_GIT_SECONDS)


class StagedScan(_Strict):
    """Bounded scan of the Git index (staged post-image) for the configured literals."""

    enabled: StrictBool = False
    patterns: tuple[StagedPattern, ...] = Field(default=(), max_length=MAX_PATTERNS)
    limits: StagedLimits = StagedLimits()

    @model_validator(mode="after")
    def _needs_patterns(self) -> StagedScan:
        if self.enabled and not self.patterns:
            raise PydanticCustomError("no_patterns", "an enabled staged scan needs a pattern")
        ids = [p.id for p in self.patterns]
        if len(ids) != len(set(ids)):
            raise PydanticCustomError("duplicate_id", "duplicate pattern id")
        return self


class CiManifest(_Strict):
    """The `decoy-ci/v1` CI manifest: strict, typed, no includes, commands, or interpolation."""

    schema_version: Literal["decoy-ci/v1"]
    pipelines: tuple[PipelineRef, ...] = Field(min_length=1, max_length=MAX_PIPELINES)
    checks: Checks = Checks()
    staged_scan: StagedScan = StagedScan()

    @model_validator(mode="after")
    def _unique_ids(self) -> CiManifest:
        pipeline_ids = [p.id for p in self.pipelines]
        if len(pipeline_ids) != len(set(pipeline_ids)):
            raise PydanticCustomError("duplicate_id", "duplicate pipeline id")
        check_ids = [
            c.id
            for group in (self.checks.drift, self.checks.evidence, self.checks.regression_suites)
            for c in group
        ]
        if len(check_ids) != len(set(check_ids)):
            raise PydanticCustomError("duplicate_id", "duplicate check id")
        selected = self.checks.validation.pipelines
        if selected is not None and not set(selected) <= set(pipeline_ids):
            raise PydanticCustomError("unknown_pipeline", "validation names an undeclared pipeline")
        return self
