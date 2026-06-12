"""Template <-> disguise legal-correspondence drift guard.

Product rule (audit H12 direction, 2026-06-12): an engine disguise is
the canonical legal artifact for its regulation, versioned on a date.
A CLI template that claims a compliance regime must be DERIVED from the
engine disguise of a specific version and must keep its field masks
equivalent to that disguise's field_rules. This guard fails when:

1. a compliance template lacks its `x-derived-from-disguise` marker;
2. the referenced disguise no longer exists, or its `version` has been
   bumped without the template being re-derived (the tripwire);
3. a template column mapped to a disguise detector uses a different
   mask strategy or different params than the disguise's first-match
   field rule, unless the (template, column) pair is listed in
   STRICTER_EXCEPTIONS with a reason.
"""

from __future__ import annotations

import re

import pytest
import yaml

from decoy.templates import get_template

from decoy_engine.disguises import load_disguises

_MARKER = re.compile(r"^# x-derived-from-disguise: ([a-z0-9_]+)@(\d{4}-\d{2}-\d{2})$")

_COMPLIANCE_TEMPLATES = ("hipaa", "pci", "gdpr")

# Template column -> disguise detector id. None = the disguise is silent
# on this column type; the template's choice is its own.
_COLUMN_DETECTOR: dict[str, dict[str, str | None]] = {
    "hipaa": {
        "first_name": "first_name",
        "last_name": "last_name",
        "street": "address",
        "city": None,
        "zip": "us_zip",
        "dob": "iso_date",
        "admission_date": "iso_date",
        "discharge_date": "iso_date",
        "phone": "us_phone",
        "fax": "fax_number",
        "email": "email",
        "ssn": "ssn",
        "mrn": "mrn",
        "health_plan_id": "health_plan_id",
        "account_number": "iban",
        "license_number": "license_num",
        "vehicle_id": "vehicle_id",
        "device_id": "device_id",
        "url": "url",
        "ip_address": "ipv4",
        "biometric_id": "biometric_id",
    },
    "pci": {
        "cardholder_name": "person_name",
        "card_number": "pan",
        "card_expiry": None,
        "cvv": "cvv",
        "billing_zip": "us_zip",
        "email": "email",
        "transaction_id": None,
        "transaction_date": "iso_date",
    },
    "gdpr": {
        "full_name": "person_name",
        "email": "email",
        "phone": "us_phone",
        "ip_address": "ipv4",
        "user_agent": None,
        "device_id": None,
        "country": None,
        "city": None,
        "postal_code": "us_zip",
        "national_id": None,
        "passport_number": None,
        "ethnicity": None,
        "religion": None,
        "health_condition": None,
        "salary": None,
    },
}

# (template, column) pairs allowed to be STRICTER than the disguise
# canonical, each with the reason recorded here.
_STRICTER_EXCEPTIONS: dict[tuple[str, str], str] = {
    ("hipaa", "ip_address"): "no ipv4 provider in the default registry; redact is strictly safer",
    ("gdpr", "ip_address"): "no ipv4 provider in the default registry; redact is strictly safer",
}

# disguise faker_type -> CLI template provider name.
_FAKER_TYPE_TO_PROVIDER = {
    "first_name": "person_first_name",
    "last_name": "person_last_name",
    "name": "person_name",
    "email": "person_email",
    "phone_number": "person_phone",
    "street_address": "address_street",
}


def _disguises():
    return {d.id: d for d in load_disguises()}


def _template_cfg(name: str) -> tuple[dict, str, str]:
    body = get_template(name).body
    first_line = body.splitlines()[0]
    m = _MARKER.match(first_line)
    assert m, (
        f"{name}.yaml must start with '# x-derived-from-disguise: <id>@<YYYY-MM-DD>' "
        f"(got {first_line!r})"
    )
    return yaml.safe_load(body), m.group(1), m.group(2)


def _first_rule_for(disguise, detector_id: str):
    for rule in disguise.field_rules:
        if detector_id in rule.detectors:
            return rule
    return None


def _equivalent(template: str, column: str, col_cfg: dict, rule) -> str | None:
    """None when the template column matches the disguise rule; else why not."""
    strategy = col_cfg.get("strategy")
    params = col_cfg.get("provider_config") or {}
    if rule.mask == "faker":
        want = _FAKER_TYPE_TO_PROVIDER.get(rule.params.get("faker_type", ""))
        if strategy != "faker":
            return f"disguise says faker, template says {strategy!r}"
        if want and col_cfg.get("provider") != want:
            return f"disguise faker_type maps to {want!r}, template uses {col_cfg.get('provider')!r}"
        return None
    if strategy != rule.mask:
        return f"disguise says {rule.mask!r}, template says {strategy!r}"
    if rule.mask == "fpe":
        if params.get("charset") != rule.params.get("charset"):
            return (
                f"fpe charset mismatch: disguise {rule.params.get('charset')!r} "
                f"vs template {params.get('charset')!r}"
            )
        if bool(params.get("validate_luhn")) != bool(rule.params.get("validate_luhn")):
            return "fpe validate_luhn mismatch"
    if rule.mask == "truncate" and params.get("length") != rule.params.get("length"):
        return (
            f"truncate length mismatch: disguise {rule.params.get('length')!r} "
            f"vs template {params.get('length')!r}"
        )
    if rule.mask == "date_shift":
        # Disguise YAML uses jitter_days: N; the handler contract is
        # min_days: -N, max_days: N.
        jitter = rule.params.get("jitter_days")
        if jitter is not None and (
            params.get("min_days") != -jitter or params.get("max_days") != jitter
        ):
            return (
                f"date_shift jitter mismatch: disguise +-{jitter}, template "
                f"[{params.get('min_days')}, {params.get('max_days')}]"
            )
    return None


class TestDerivationMarkers:
    @pytest.mark.parametrize("name", _COMPLIANCE_TEMPLATES)
    def test_marker_present_and_disguise_exists(self, name: str):
        _cfg, disguise_id, _version = _template_cfg(name)
        assert disguise_id in _disguises(), f"unknown disguise {disguise_id!r}"

    @pytest.mark.parametrize("name", _COMPLIANCE_TEMPLATES)
    def test_pinned_version_matches_live_disguise(self, name: str):
        """THE TRIPWIRE: bumping a disguise's dated version without
        re-deriving the dependent template must fail CI."""
        _cfg, disguise_id, pinned = _template_cfg(name)
        live = _disguises()[disguise_id].version
        assert pinned == live, (
            f"{name}.yaml pins {disguise_id}@{pinned} but the live disguise is "
            f"{disguise_id}@{live}. Re-derive the template against the new disguise "
            f"version (check every field rule), then update the pin."
        )


class TestFieldRuleCorrespondence:
    @pytest.mark.parametrize("name", _COMPLIANCE_TEMPLATES)
    def test_every_mapped_column_matches_its_disguise_rule(self, name: str):
        cfg, disguise_id, _version = _template_cfg(name)
        disguise = _disguises()[disguise_id]
        mapping = _COLUMN_DETECTOR[name]
        columns = {c["name"]: c for t in cfg["tables"] for c in t.get("columns", [])}
        # The mapping table itself must stay in step with the template.
        assert set(columns) == set(mapping), (
            f"{name}: template columns and _COLUMN_DETECTOR diverge: "
            f"{set(columns) ^ set(mapping)}"
        )
        problems: list[str] = []
        for col_name, detector_id in mapping.items():
            if detector_id is None:
                continue
            rule = _first_rule_for(disguise, detector_id)
            if rule is None:
                problems.append(f"{col_name}: detector {detector_id!r} has no disguise rule")
                continue
            why = _equivalent(name, col_name, columns[col_name], rule)
            if why is not None and (name, col_name) not in _STRICTER_EXCEPTIONS:
                problems.append(f"{col_name}: {why}")
        assert not problems, (
            f"{name}.yaml drifted from disguise {disguise_id!r}:\n  " + "\n  ".join(problems)
        )

    def test_stricter_exceptions_all_carry_reasons(self):
        for key, reason in _STRICTER_EXCEPTIONS.items():
            assert reason.strip(), f"{key} needs a recorded reason"
