"""Every bundled template must validate AND run, end to end.

Audit H5 regression net (2026-06-12): 3 of the 5 shipped templates
(hipaa/pci/gdpr) crashed at `decoy run` with provider_not_poolable while
`decoy validate` exited 0 -- the compliance starters were dead on
arrival and nothing in CI exercised them against data. These cells
synthesize an input CSV from each template's own column list and demand
exit 0 from BOTH verbs, plus spot semantic checks on the strategies the
rewrite introduced (fpe format preservation, truncate depth, hash
determinism).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.templates import get_template, list_templates
from tests.generate_industry_templates import GENERATE_INDUSTRY_TEMPLATES
from tests.keyed_secret import TEST_MASK_SECRET_REF

runner = CliRunner()

# Sample values keyed by column name. Shapes matter: dates must parse,
# the PAN must be Luhn-valid (fpe validate_luhn), the VIN is 17-char.
_SAMPLE_VALUES: dict[str, list[str]] = {
    "first_name": ["Alice", "Bob", "Carol"],
    "last_name": ["Ames", "Burke", "Cole"],
    "full_name": ["Alice Ames", "Bob Burke", "Carol Cole"],
    "cardholder_name": ["Alice Ames", "Bob Burke", "Carol Cole"],
    "street": ["1 Main St", "2 Oak Ave", "3 Pine Rd"],
    "city": ["Springfield", "Riverton", "Lakeside"],
    "zip": ["12345", "23456", "34567"],
    "billing_zip": ["12345", "23456", "34567"],
    "postal_code": ["12345", "23456", "34567"],
    "dob": ["1980-01-15", "1992-06-30", "1975-11-02"],
    "admission_date": ["2026-01-10", "2026-02-14", "2026-03-20"],
    "discharge_date": ["2026-01-12", "2026-02-20", "2026-03-25"],
    "transaction_date": ["2026-04-01", "2026-04-02", "2026-04-03"],
    "phone": ["(212) 555-0101", "(212) 555-0102", "(212) 555-0103"],
    "fax": ["(212) 555-0201", "(212) 555-0202", "(212) 555-0203"],
    "email": ["a@example.com", "b@example.com", "c@example.com"],
    "ssn": ["111-22-3333", "444-55-6666", "777-88-9999"],
    "mrn": ["MRN001A", "MRN002B", "MRN003C"],
    "health_plan_id": ["HP-1001", "HP-1002", "HP-1003"],
    "account_number": ["AC10001", "AC10002", "AC10003"],
    "license_number": ["LIC-100", "LIC-200", "LIC-300"],
    "vehicle_id": ["1HGBH41JXMN109186", "2HGBH41JXMN109187", "3HGBH41JXMN109188"],
    "device_id": ["dev-aaa-1", "dev-bbb-2", "dev-ccc-3"],
    "url": ["https://x.test/1", "https://x.test/2", "https://x.test/3"],
    "ip_address": ["10.0.0.1", "10.0.0.2", "10.0.0.3"],
    "biometric_id": ["bio-1", "bio-2", "bio-3"],
    # Luhn-valid test PANs.
    "card_number": ["4111111111111111", "5500005555555559", "340000000000009"],
    "card_expiry": ["12/27", "06/28", "09/29"],
    "cvv": ["123", "456", "789"],
    "transaction_id": ["c0ffee01", "c0ffee02", "c0ffee03"],
    "user_agent": ["Mozilla/5.0 A", "Mozilla/5.0 B", "Mozilla/5.0 C"],
    "country": ["US", "DE", "FR"],
    "national_id": ["NID-1", "NID-2", "NID-3"],
    "passport_number": ["P1234567", "P2345678", "P3456789"],
    "ethnicity": ["x", "y", "z"],
    "religion": ["x", "y", "z"],
    "health_condition": ["x", "y", "z"],
    "salary": ["50000", "60000", "70000"],
    "customer_id": ["C1", "C2", "C3"],
    "account_status": ["active", "lapsed", "active"],
}

_MASK_TEMPLATES = ("minimal", "hipaa", "pci", "gdpr")
# Keyed templates need a mask secret, supplied the way a user does (`--mask-secret`);
# test_keyed_secret_guidance.py pins this set against the engine's own classifier.
_KEYED = frozenset({"hipaa", "pci", "gdpr"})


def _run_args(name: str, config_path: Path) -> list[str]:
    args = ["run", str(config_path)]
    return [*args, "--mask-secret", TEST_MASK_SECRET_REF] if name in _KEYED else args


def _materialize(name: str, tmp_path: Path) -> tuple[Path, Path, dict]:
    """Write the template + a synthesized input CSV into tmp_path.

    Returns (config_path, output_path, config_dict).
    """
    cfg = yaml.safe_load(get_template(name).body)
    out_path: Path | None = None
    for src in cfg.get("sources", {}).values():
        in_path = tmp_path / Path(src["path"]).name
        src["path"] = str(in_path)
        columns = [c["name"] for t in cfg["tables"] for c in t.get("columns", [])]
        if columns:  # mask templates synthesize their own input
            missing = [c for c in columns if c not in _SAMPLE_VALUES]
            assert not missing, f"add sample values for template columns: {missing}"
            pd.DataFrame({c: _SAMPLE_VALUES[c] for c in columns}).to_csv(in_path, index=False)
    for tgt in cfg.get("targets", {}).values():
        out_path = tmp_path / Path(tgt["path"]).name
        tgt["path"] = str(out_path)
    config_path = tmp_path / f"{name}.yaml"
    config_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    assert out_path is not None
    return config_path, out_path, cfg


class TestEveryTemplateValidatesAndRuns:
    def test_registry_has_the_expected_set(self):
        assert [t.name for t in list_templates()] == [
            "minimal",
            "hipaa",
            "pci",
            "gdpr",
            "generate",
            *GENERATE_INDUSTRY_TEMPLATES,
        ]

    @pytest.mark.parametrize("name", _MASK_TEMPLATES)
    def test_mask_template_validate_then_run(self, name: str, tmp_path: Path, mask_secret: str):
        config_path, out_path, _cfg = _materialize(name, tmp_path)

        validate = runner.invoke(app, ["validate", "config", str(config_path)])
        assert validate.exit_code == 0, f"{name}: validate failed:\n{validate.output}"

        run = runner.invoke(app, _run_args(name, config_path))
        assert run.exit_code == 0, f"{name}: run failed:\n{run.output}"
        assert out_path.exists(), f"{name}: no output written"
        out = pd.read_csv(out_path, dtype=str)
        assert len(out) == 3, f"{name}: row count not preserved"

    def test_generate_template_validate_then_run(self, tmp_path: Path):
        cfg = yaml.safe_load(get_template("generate").body)
        out_path = None
        for tgt in cfg.get("targets", {}).values():
            out_path = tmp_path / Path(tgt["path"]).name
            tgt["path"] = str(out_path)
        config_path = tmp_path / "generate.yaml"
        config_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

        validate = runner.invoke(app, ["validate", "config", str(config_path)])
        assert validate.exit_code == 0, f"generate: validate failed:\n{validate.output}"
        run = runner.invoke(app, ["run", str(config_path)])
        assert run.exit_code == 0, f"generate: run failed:\n{run.output}"
        assert out_path is not None and out_path.exists()


class TestRewrittenStrategySemantics:
    """Spot checks on the strategies the H5/H12 rewrite introduced."""

    def test_hipaa_semantics(self, tmp_path: Path, mask_secret: str):
        config_path, out_path, _cfg = _materialize("hipaa", tmp_path)
        assert runner.invoke(app, _run_args("hipaa", config_path)).exit_code == 0
        out = pd.read_csv(out_path, dtype=str)
        src = pd.DataFrame({c: _SAMPLE_VALUES[c] for c in out.columns})

        # zip truncated to the leading 3 digits.
        assert list(out["zip"]) == [v[:3] for v in src["zip"]]
        # ssn: format preserved (9 digits + dashes), value changed.
        for masked, original in zip(out["ssn"], src["ssn"]):
            assert masked != original
            assert len(masked) == len(original)
            assert masked.replace("-", "").isdigit()
        # date columns still parse as dates.
        for col in ("dob", "admission_date", "discharge_date"):
            assert pd.to_datetime(out[col], errors="coerce").notna().all(), col
        # redact columns carry no source values.
        for col in ("device_id", "biometric_id", "health_plan_id", "license_number"):
            assert not set(out[col]) & set(src[col]), col

    def test_pci_pan_luhn_valid_and_deterministic(self, tmp_path: Path, mask_secret: str):
        def luhn_ok(number: str) -> bool:
            digits = [int(d) for d in number]
            odd = digits[-1::-2]
            even = [sum(divmod(2 * d, 10)) for d in digits[-2::-2]]
            return (sum(odd) + sum(even)) % 10 == 0

        config_path, out_path, _cfg = _materialize("pci", tmp_path)
        assert runner.invoke(app, _run_args("pci", config_path)).exit_code == 0
        first = pd.read_csv(out_path, dtype=str)
        for masked, original in zip(first["card_number"], _SAMPLE_VALUES["card_number"]):
            assert masked != original
            assert len(masked) == len(original) and masked.isdigit()
            assert luhn_ok(masked), f"fpe PAN {masked} fails Luhn"
        # Deterministic: a second run with the same seed is byte-identical
        # for the keyed columns.
        assert runner.invoke(app, _run_args("pci", config_path)).exit_code == 0
        second = pd.read_csv(out_path, dtype=str)
        assert list(first["transaction_id"]) == list(second["transaction_id"])
        assert list(first["card_number"]) == list(second["card_number"])

    def test_gdpr_device_id_pseudonymised(self, tmp_path: Path, mask_secret: str):
        config_path, out_path, _cfg = _materialize("gdpr", tmp_path)
        assert runner.invoke(app, _run_args("gdpr", config_path)).exit_code == 0
        out = pd.read_csv(out_path, dtype=str)
        assert not set(out["device_id"]) & set(_SAMPLE_VALUES["device_id"])
        assert list(out["postal_code"]) == [v[:3] for v in _SAMPLE_VALUES["postal_code"]]


# --- generate starter templates (GEN-CATALOG GC2, QA check GEN-14) ---
# Registry-driven: a seventh template is covered the day it is added. The catalog guard fails
# here, not at a user's run, when the engine renames a type or a faker provider.

SMALL_ROWS = 30


def _generate_names() -> list[str]:
    names = []
    for t in list_templates():
        cfg = yaml.safe_load(t.body)
        tables = cfg.get("tables") or []
        if tables and all(tb.get("generate_columns") for tb in tables):
            names.append(t.name)
    return names


def test_the_six_industry_templates_are_registered():
    names = set(_generate_names())
    assert set(GENERATE_INDUSTRY_TEMPLATES) <= names


@pytest.mark.parametrize("name", _generate_names())
def test_generate_template_validates_runs_and_links_keys(name: str, tmp_path: Path):
    cfg = yaml.safe_load(get_template(name).body)
    for table in cfg["tables"]:
        table["row_count"] = SMALL_ROWS
    for target in cfg["targets"].values():
        target["path"] = str(tmp_path / Path(target["path"]).name)
    config_path = tmp_path / f"{name}.yaml"
    config_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")

    # The whole gate, the command a user runs, not only the config check.
    validate = runner.invoke(app, ["validate", str(config_path)])
    assert validate.exit_code == 0, f"{name}: validate failed:\n{validate.output}"
    run = runner.invoke(app, ["run", str(config_path)])
    assert run.exit_code == 0, f"{name}: run failed:\n{run.output}"

    frames = {n: pd.read_csv(Path(t["path"]), dtype=str) for n, t in cfg["targets"].items()}
    for table in cfg["tables"]:
        assert len(frames[table["name"]]) == SMALL_ROWS
    links = 0
    for table in cfg["tables"]:
        for col in table["generate_columns"]:
            if col["type"] == "reference":
                links += 1
                child = frames[table["name"]][col["name"]].dropna()
                parent = set(frames[col["reference_table"]][col["reference_column"]])
                assert set(child) <= parent, f"{name}: {table['name']}.{col['name']} not linked"
    if name in GENERATE_INDUSTRY_TEMPLATES:
        assert links >= 1, f"{name}: an industry template must declare at least one foreign key"


@pytest.mark.parametrize("name", _generate_names())
def test_generate_template_uses_only_catalog_types(name: str):
    from decoy_engine import code_set_catalog, list_generate_faker_providers
    from decoy_engine.config import generate_option_catalog

    catalog = generate_option_catalog()
    fakers = set(list_generate_faker_providers())
    cfg = yaml.safe_load(get_template(name).body)
    for table in cfg["tables"]:
        for col in table["generate_columns"]:
            assert col["type"] in catalog, f"{name}.{col['name']}: unknown type {col['type']}"
            spec = catalog[col["type"]]
            known = {*spec.required, *spec.optional, *spec.common, "name", "type"}
            assert set(col) <= known, f"{name}.{col['name']}: unknown option {set(col) - known}"
            assert set(spec.required) <= set(col), f"{name}.{col['name']}: missing required"
            if col["type"] == "faker":
                assert col["faker_type"] in fakers, f"{name}.{col['name']}: {col['faker_type']}"
            if spec.one_of:
                given = [k for k in spec.one_of if k in col]
                assert len(given) == 1, f"{name}.{col['name']}: give exactly one of {spec.one_of}"
            if "codeset" in col:
                assert col["codeset"] in code_set_catalog(), f"{name}.{col['name']}: codeset"


def test_generate_templates_carry_no_real_looking_seeds():
    for name in GENERATE_INDUSTRY_TEMPLATES:
        body = get_template(name).body
        assert "x-derived-from-disguise" not in body
        assert "snapshot_file" not in body


@pytest.mark.parametrize("name", GENERATE_INDUSTRY_TEMPLATES)
def test_industry_template_key_columns_are_all_references(name: str):
    """A column named like another table's key must be a `reference`, never a free column."""
    cfg = yaml.safe_load(get_template(name).body)
    keys = {t["name"]: t["generate_columns"][0]["name"] for t in cfg["tables"]}
    for table in cfg["tables"]:
        for col in table["generate_columns"][1:]:
            owners = [t for t, key in keys.items() if key == col["name"] and t != table["name"]]
            if owners:
                assert col["type"] == "reference", f"{name}.{table['name']}.{col['name']}"
                assert col["reference_table"] == owners[0]


def _generated_frames(name: str, tmp_path: Path) -> tuple[dict, dict[str, pd.DataFrame]]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    cfg = yaml.safe_load(get_template(name).body)
    for table in cfg["tables"]:
        table["row_count"] = SMALL_ROWS
    for target in cfg["targets"].values():
        target["path"] = str(tmp_path / Path(target["path"]).name)
    config_path = tmp_path / f"{name}.yaml"
    config_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    run = runner.invoke(app, ["run", str(config_path)])
    assert run.exit_code == 0, f"{name}: run failed:\n{run.output}"
    frames = {n: pd.read_csv(Path(t["path"]), dtype=str) for n, t in cfg["targets"].items()}
    return cfg, frames


def _all_match(series: pd.Series, pattern: str) -> bool:
    import re

    return bool(len(series)) and all(
        isinstance(v, str) and re.fullmatch(pattern, v) for v in series
    )


def test_industry_templates_apply_lookup_codesets(tmp_path: Path):
    _, health = _generated_frames("generate-healthcare", tmp_path / "h")
    assert _all_match(health["claims"]["diagnosis_code"], r"[A-Z][0-9][0-9A-Z].*")
    assert _all_match(health["claims"]["procedure_code"], r"[A-Z][0-9]{4}")
    _, bank = _generated_frames("generate-banking", tmp_path / "b")
    assert _all_match(bank["transactions"]["merchant_category"], r"[0-9]{4}")


@pytest.mark.parametrize("name", _generate_names())
def test_industry_template_money_columns_are_two_decimal_in_range(name: str, tmp_path: Path):
    cfg, frames = _generated_frames(name, tmp_path)
    for table in cfg["tables"]:
        for col in table["generate_columns"]:
            if col["type"] == "distribution":
                assert col.get("output_type") == "decimal(2)", f"{name}.{col['name']}"
                values = frames[table["name"]][col["name"]]
                assert _all_match(values, r"-?[0-9]+\.[0-9]{2}")
                assert all(col["low"] <= float(v) <= col["high"] for v in values)
