"""STORM detector-id -> mask strategy mapping for `decoy init` scaffolding.

OSS.4c (2026-06-02). Provides the small static table that `decoy init <file>`
uses when scaffolding a pipeline.yaml from a STORM scan. Every column the
scanner profiled gets ONE strategy entry written into the starter YAML; the
mapping below names the candidate strategy + provider, AND the REVIEW reason
the user must read before running the pipeline.

Source patterns (cited per the "use established methodology" rule):

  - dbt init (https://docs.getdbt.com/reference/commands/init):
    scaffolds a starter project from a template, asks the user to
    review the output before using it. Our analog: scaffold the
    starter pipeline.yaml; the user reviews the REVIEW: comments.
  - cookiecutter (https://cookiecutter.readthedocs.io):
    template-driven scaffolding. Our analog: every column is
    rendered through this inference map; the table IS the
    template.

The table is intentionally SHORT (~20 entries at first cut). The
project does not promise a strategy for every conceivable detector;
the long tail falls into the `_FALLBACK` branch and writes a louder
REVIEW comment so the user knows they have to make the call. The
table grows as STORM ships new detectors AND we have a good
default for them.

Wiring: `_infer_strategy_for_column(fs: FieldStats) -> Inference` is
the only function `decoy init` calls. It returns an `Inference`
dataclass carrying the strategy name, optional provider name, and
the REVIEW reason string the YAML emitter must place above the
column entry. The strategy + provider names match what
`decoy_engine.execution._strategies.SCALAR_HANDLERS` and
`decoy_engine.providers_v2.get_default_registry()` ship today.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Inference:
    """The pipeline-YAML choice for one column.

    Fields:
        strategy: the mask strategy name (faker, hash, redact, etc.).
        provider: the faker provider name (only set when strategy is
            'faker'; None otherwise).
        review: the human-readable reason this choice was made. The
            YAML emitter writes this above the column entry as a
            `# REVIEW: <review>` comment so the user knows what the
            scaffolder inferred and what they must check.
        deterministic: when True, the YAML entry carries
            `deterministic: true` (used for FK-preservation paths,
            e.g. customer_id-shaped columns).
    """

    strategy: str
    provider: str | None = None
    review: str = ""
    deterministic: bool = False


# Detector-id -> Inference. Detector ids come from STORM's detectors
# (`decoy_engine.storm.detectors`). The table is intentionally a
# narrow subset; the long tail goes through `_FALLBACK`.
#
# The REVIEW reason is the operator-facing copy that lands in the
# generated YAML. Keep it short, factual, and actionable. "Detected
# X; review whether Y is the right strategy" is the canonical shape.
_INFERENCE_TABLE: dict[str, Inference] = {
    "email": Inference(
        strategy="faker",
        provider="person_email",
        review="STORM detected email addresses. Faker replaces with synthetic emails.",
    ),
    "ssn": Inference(
        strategy="hash",
        review=(
            "STORM detected SSNs. Hash preserves joinability without exposing the "
            "value. If you need real-shape output (333-22-4444), use "
            "provider: synthetic_ssn instead."
        ),
    ),
    "us_phone": Inference(
        strategy="faker",
        provider="person_phone",
        review="STORM detected US phone numbers. Faker replaces with synthetic phone.",
    ),
    "person_name": Inference(
        strategy="faker",
        provider="person_full_name",
        review=(
            "STORM detected person names. Faker replaces with synthetic names. "
            "If this column is a first OR last name only, swap the provider to "
            "person_first_name or person_last_name."
        ),
    ),
    "iso_date": Inference(
        strategy="date_shift",
        review=(
            "STORM detected ISO-format dates. date_shift shifts each date by "
            "an independent per-value offset in [min_days, max_days] (same "
            "source value always gets the same shift, but shifts are NOT "
            "globally order-preserving across rows). Defaults are "
            "min_days: -365 / max_days: 365; tune via provider_config."
        ),
    ),
    "us_date": Inference(
        strategy="date_shift",
        review=(
            "STORM detected US-format dates. date_shift shifts each date by "
            "an independent per-value offset in [min_days, max_days] (not "
            "order-preserving across rows). Defaults are -365/+365 days; "
            "tune via provider_config."
        ),
    ),
    "us_zip": Inference(
        strategy="truncate",
        review=(
            "STORM detected US ZIP codes. truncate to 3 digits matches HIPAA "
            "Safe Harbor; if your downstream needs full ZIP, use faker + "
            "provider: address_zip instead."
        ),
    ),
    "address_street": Inference(
        strategy="faker",
        provider="address_street",
        review="STORM detected street addresses. Faker replaces with synthetic addresses.",
    ),
    "address_city": Inference(
        strategy="faker",
        provider="address_city",
        review="STORM detected city names. Faker replaces with synthetic cities.",
    ),
    "mrn": Inference(
        strategy="hash",
        review=(
            "STORM detected medical record numbers. Hash preserves joinability. "
            "If you need real-shape output, use provider: synthetic_mrn."
        ),
    ),
    "npi": Inference(
        strategy="hash",
        review=(
            "STORM detected NPI numbers. Hash preserves joinability. "
            "If you need real-shape output, use provider: synthetic_npi."
        ),
    ),
    "ndc": Inference(
        strategy="hash",
        review=(
            "STORM detected NDC codes. Hash preserves joinability. "
            "If you need real-shape output, use provider: synthetic_ndc."
        ),
    ),
    "icd10": Inference(
        strategy="truncate",
        review=(
            "STORM detected ICD-10 codes. truncate to 3 chars (category) "
            "matches HIPAA Safe Harbor."
        ),
    ),
    "pan": Inference(
        strategy="fpe",
        review=(
            "STORM detected payment card numbers (PAN). fpe (format-preserving "
            "encryption) keeps Luhn-valid shape; no per-column key config "
            "needed -- the FPE key is derived automatically per job/namespace."
        ),
    ),
    "cvv": Inference(
        strategy="redact",
        review=(
            "STORM detected CVV. PCI DSS 3.3 requires CVV not be stored "
            "post-authorization; redact removes the value entirely."
        ),
    ),
    "iban": Inference(
        strategy="hash",
        review=(
            "STORM detected IBANs. Hash preserves joinability. If you need "
            "real-shape output, use provider: synthetic_iban."
        ),
    ),
    "uuid": Inference(
        strategy="faker",
        provider="uuid",
        review="STORM detected UUIDs. Faker generates fresh synthetic UUIDs.",
    ),
    "ipv4": Inference(
        strategy="redact",
        review=(
            "STORM detected IPv4 addresses. redact removes the value; if you "
            "need realistic IP-shaped output for analytics, swap to faker + "
            "provider: random_choice over a known IP range."
        ),
    ),
}


# Used when no detector matched OR the column doesn't have a clear default.
_FALLBACK = Inference(
    strategy="redact",
    review=(
        "STORM did not flag this column as a known PII type. redact is the "
        "safe default; replace with passthrough if this column is intentionally "
        "kept verbatim, or pick a more appropriate strategy if your data "
        "carries PII the detectors missed."
    ),
)


# Used when multiple detectors fire on the same column with comparable
# confidence (e.g. a column that looks like a phone AND a date).
_AMBIGUOUS_TEMPLATE = (
    "STORM detected multiple candidate signals ({signals}). The scaffolder "
    "picked {chosen} but the column may need a different strategy; review "
    "before running."
)


def _infer_strategy_for_column(field_stats) -> Inference:
    """Pick a strategy for one column based on its STORM FieldStats.

    Decision order:
      1. If the column has at least one detector match with confidence
         in {high, medium}, pick the strategy from the inference table
         keyed on the highest-confidence detector_id. If multiple
         detectors fire at comparable confidence, use the AMBIGUOUS
         template so the REVIEW comment names every candidate.
      2. If no detector match (or all are low confidence) and the
         column is integer + likely unique, suggest hash (treat as
         a potential FK key) with a louder REVIEW asking the user
         to confirm.
      3. Otherwise return _FALLBACK (redact + verbose review).

    The function reads only public attributes on FieldStats; it does
    not import from decoy_engine. Callers pass the FieldStats they
    already obtained from run_storm.
    """
    matches = getattr(field_stats, "detector_matches", None) or []
    confident_matches = [
        m for m in matches
        if getattr(m, "confidence_bucket", None) in ("high", "medium")
        or getattr(m, "match_rate", 0.0) >= 0.5
    ]

    if confident_matches:
        # Pick the highest match_rate among confident matches. If two
        # are within 0.1 of each other, treat as ambiguous and write
        # the AMBIGUOUS template review (still pick the top one).
        confident_matches.sort(key=lambda m: -getattr(m, "match_rate", 0.0))
        top = confident_matches[0]
        top_id = getattr(top, "detector_id", "")
        ambiguous = (
            len(confident_matches) > 1
            and (
                getattr(top, "match_rate", 0.0)
                - getattr(confident_matches[1], "match_rate", 0.0)
            )
            < 0.1
        )
        base = _INFERENCE_TABLE.get(top_id, _FALLBACK)
        if ambiguous:
            signals = ", ".join(
                getattr(m, "detector_id", "?") for m in confident_matches[:3]
            )
            review = _AMBIGUOUS_TEMPLATE.format(
                signals=signals, chosen=base.strategy
            )
            return Inference(
                strategy=base.strategy,
                provider=base.provider,
                review=review,
                deterministic=base.deterministic,
            )
        return base

    # No confident detector match. Treat likely-unique integer columns
    # as potential FK keys + suggest hash so joins survive.
    if (
        getattr(field_stats, "inferred_type", "") == "integer"
        and getattr(field_stats, "is_likely_unique", False)
    ):
        return Inference(
            strategy="hash",
            review=(
                "No PII detector fired, but this column is a likely-unique "
                "integer (possible FK key). Hash preserves joinability; "
                "replace with passthrough if the column should be kept "
                "verbatim, or with faker if a real-shape replacement is "
                "preferred."
            ),
        )

    return _FALLBACK


__all__ = [
    "_FALLBACK",
    "_INFERENCE_TABLE",
    "Inference",
    "_infer_strategy_for_column",
]
