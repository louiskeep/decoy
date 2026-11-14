"""What a user sees when a keyed pipeline has no mask secret, on every CLI surface.

Engine 0.17.0 refuses a keyed strategy without an admitted secret
(`keyed_strategy_requires_secret`); there is no job_seed fallback. The engine's own text
names its Python API (`run(key_provider=...)`), which a CLI user cannot act on, so the CLI
replaces it with one fixed message per surface that names `--mask-secret` /
`global_settings.mask_secret_ref` and the `env:` / `file:` forms. Fixed text means
closed-set: no value, path or exception prose can ride along.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_USAGE
from decoy.templates import get_template, list_templates
from tests.csv_sources import csv_source
from tests.keyed_secret import TEST_MASK_SECRET, TEST_MASK_SECRET_REF, with_mask_secret

runner = CliRunner()

CODE = "keyed_strategy_requires_secret"
_ENGINE_API_SPEAK = ("key_provider", "run(", "Traceback", "job_seed")


def _keyed_pipeline(tmp_path: Path, *, strategy: str = "fpe", secret: bool = False) -> Path:
    src = tmp_path / "accounts.csv"
    pd.DataFrame({"ssn": ["123456789", "987654321", "111223333"]}).to_csv(src, index=False)
    column: dict = {"name": "ssn", "strategy": strategy, "namespace": "ssn_ns"}
    if strategy == "fpe":
        column["provider_config"] = {"charset": "digits"}
    cfg: dict = {
        "version": 2,
        "global_settings": {"seed": 42},
        "sources": {"accounts": csv_source(src)},
        "tables": [{"name": "accounts", "columns": [column]}],
        "targets": {
            "accounts": {"type": "file", "format": "csv", "path": str(tmp_path / "out.csv")}
        },
    }
    if secret:
        with_mask_secret(cfg)
    path = tmp_path / "pipeline.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _assert_actionable(text: str, *, flag: bool) -> None:
    assert CODE in text, text
    assert "global_settings.mask_secret_ref" in text, text
    assert "env:" in text and "file:" in text, text
    assert "decoy explain keys" in text, text
    assert ("--mask-secret" in text) is flag, text
    for word in _ENGINE_API_SPEAK:
        assert word not in text, f"{word!r} leaked into: {text}"


# ---- decoy run --------------------------------------------------------------------------


@pytest.mark.parametrize("strategy", ["fpe", "hash"])
def test_run_refusal_is_usage_and_names_the_cli_remedy(tmp_path: Path, strategy: str) -> None:
    cfg = _keyed_pipeline(tmp_path, strategy=strategy)
    result = runner.invoke(app, ["run", str(cfg)])
    assert result.exit_code == EXIT_USAGE, result.output
    _assert_actionable(result.output, flag=True)
    assert str(tmp_path) not in result.output
    assert not (tmp_path / "out.csv").exists()


def test_run_refusal_json_error_is_the_same_fixed_text(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    errors = []
    for sub, strategy in (("a", "fpe"), ("b", "hash")):
        result = runner.invoke(
            app, ["run", str(_keyed_pipeline(tmp_path / sub, strategy=strategy)), "--json"]
        )
        assert result.exit_code == EXIT_USAGE, result.output
        payload = json.loads(result.stdout)
        assert payload["status"] == "error"
        errors.append(payload["error"])
    _assert_actionable(errors[0], flag=True)
    assert str(tmp_path) not in errors[0]
    assert errors[0] == errors[1], "the refusal must be one closed-set text, not per-pipeline prose"


def test_run_refusal_chunked_matches_plain(tmp_path: Path) -> None:
    (tmp_path / "p").mkdir()
    (tmp_path / "c").mkdir()
    plain = runner.invoke(app, ["run", str(_keyed_pipeline(tmp_path / "p")), "--json"])
    chunked = runner.invoke(
        app, ["run", str(_keyed_pipeline(tmp_path / "c")), "--chunked", "--json"]
    )
    assert plain.exit_code == chunked.exit_code == EXIT_USAGE, (plain.output, chunked.output)
    assert json.loads(plain.stdout)["error"] == json.loads(chunked.stdout)["error"]


# ---- decoy unmask -----------------------------------------------------------------------


def test_unmask_refusal_is_usage_and_names_the_config_key(tmp_path: Path, mask_secret: str) -> None:
    cfg = _keyed_pipeline(tmp_path)
    assert runner.invoke(app, ["run", str(cfg), "--mask-secret", mask_secret]).exit_code == 0
    result = runner.invoke(app, ["unmask", str(cfg), str(tmp_path / "out.csv")])
    assert result.exit_code == EXIT_USAGE, result.output
    # `decoy unmask` takes --mask-secret too, so its remedy names the flag and the config key.
    _assert_actionable(result.output, flag=True)
    assert "unmask failed" not in result.output
    assert not (tmp_path / "out.unmasked.csv").exists()


# ---- the mask() library API -------------------------------------------------------------


def test_mask_api_raises_its_documented_error_with_the_api_remedy(tmp_path: Path) -> None:
    from decoy.api import MaskSecretConfigError, mask

    with pytest.raises(MaskSecretConfigError) as info:
        mask(config=_keyed_pipeline(tmp_path))
    text = str(info.value)
    assert CODE in text and "mask_secret=" in text and "global_settings.mask_secret_ref" in text
    assert "env:" in text and "file:" in text
    for word in _ENGINE_API_SPEAK:
        assert word not in text, f"{word!r} leaked into: {text}"


# ---- the secret never reaches output ----------------------------------------------------


def test_the_test_secret_never_appears_in_any_output(tmp_path: Path, mask_secret: str) -> None:
    cfg = _keyed_pipeline(tmp_path)
    for args in (["--json"], ["--verbose"], []):
        result = runner.invoke(app, ["run", str(cfg), "--mask-secret", mask_secret, *args])
        assert result.exit_code == 0, result.output
        assert TEST_MASK_SECRET not in result.output
    assert TEST_MASK_SECRET not in (tmp_path / "out.csv").read_text(encoding="utf-8")
    assert TEST_MASK_SECRET_REF == mask_secret


# ---- decoy init and the bundled templates -----------------------------------------------


def _engine_says_keyed(body: str) -> bool:
    from decoy_engine.secret_providers import secret_requirements_for_config

    return bool(secret_requirements_for_config(yaml.safe_load(body)))


def test_keyed_templates_say_a_secret_is_required_and_unkeyed_do_not() -> None:
    keyed = []
    for template in list_templates():
        body = get_template(template.name).body
        if _engine_says_keyed(body):
            keyed.append(template.name)
            assert "a mask secret is REQUIRED" in body, template.name
            assert "--mask-secret env:DECOY_MASK_SECRET" in body, template.name
            assert "mask_secret_ref" in body and "file:" in body, template.name
            assert "openssl rand -hex 32" in body, template.name
            assert "decoy explain keys" in body, template.name
        else:
            assert "REQUIRED" not in body, template.name
    assert sorted(keyed) == ["gdpr", "hipaa", "pci"]


@pytest.mark.parametrize(("preset", "keyed"), [("pci", True), ("minimal", False)])
def test_init_preset_next_steps_name_the_secret_only_when_keyed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, preset: str, keyed: bool
) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        app, ["init", "--preset", preset, "-y", "-o", "pipeline.yaml"], input="\n\n"
    )
    assert result.exit_code == 0, result.output
    assert ("--mask-secret env:DECOY_MASK_SECRET" in result.output) is keyed, result.output
    assert ("decoy explain keys" in result.output) is keyed, result.output


def test_init_scaffold_of_a_keyed_file_names_the_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    pd.DataFrame(
        {"card_number": ["4111111111111111", "5500005555555559", "340000000000009"] * 10}
    ).to_csv(tmp_path / "cards.csv", index=False)
    result = runner.invoke(app, ["init", "cards.csv", "-y", "-o", "pipeline.yaml"])
    assert result.exit_code == 0, result.output
    body = (tmp_path / "pipeline.yaml").read_text(encoding="utf-8")
    assert _engine_says_keyed(body), body
    assert "a mask secret is REQUIRED" in body
    assert "--mask-secret env:DECOY_MASK_SECRET" in result.output, result.output


# ---- decoy explain keys -----------------------------------------------------------------


def test_explain_keys_says_required_and_how_to_make_one() -> None:
    result = runner.invoke(app, ["explain", "keys", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    text = payload["summary"] + "\n" + payload["body"]
    assert "required" in payload["summary"].lower(), payload["summary"]
    assert "openssl rand -hex 32" in text
    assert "--mask-secret env:DECOY_MASK_SECRET" in text


def test_unmask_unresolvable_secret_ref_is_usage_not_runtime(
    tmp_path: Path, mask_secret: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _keyed_pipeline(tmp_path, secret=True)
    assert runner.invoke(app, ["run", str(cfg)]).exit_code == 0
    monkeypatch.delenv("DECOY_TEST_MASK_SECRET")
    result = runner.invoke(app, ["unmask", str(cfg), str(tmp_path / "out.csv")])
    assert result.exit_code == EXIT_USAGE, result.output
    assert "missing_mask_secret" in result.output, result.output
    assert "unmask failed" not in result.output


# ---- no surface still says the public seed is the key -----------------------------------


@pytest.mark.parametrize("args", [["unmask", "--help"], ["explain", "vault"]])
def test_reversal_help_names_the_mask_secret_not_the_seed(args: list[str]) -> None:
    result = runner.invoke(app, args, env={"COLUMNS": "200"})
    assert result.exit_code == 0, result.output
    flat = " ".join(result.output.split())
    assert "mask_secret_ref" in flat, flat
    for stale in ("config's seed", "run's seed", "seed + namespace", "(seed + namespace)"):
        assert stale not in flat, f"{stale!r} in: {flat}"


# ---- every route shows its own fixed text, not the engine's -----------------------------


def _vaulted_pipeline(tmp_path: Path, *, secret: bool) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    cfg_path = _keyed_pipeline(tmp_path, strategy="hash", secret=secret)
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    cfg["tables"][0]["columns"][0]["vault"] = True
    cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return cfg_path


@pytest.mark.parametrize(
    "route",
    ["run", "run --chunked", "run --vault", "unmask", "unmask --vault", "report vault"],
)
def test_every_route_prints_its_fixed_refusal_text(
    tmp_path: Path, mask_secret: str, route: str
) -> None:
    """Each route raises the engine's KeyedStrategyRequiresSecret unwrapped on 0.17.0; each
    must swap it for its own constant, so a regression on one route cannot hide behind another."""
    from decoy import _mask_secret_guidance as guidance

    # A real masked file and vault, written under the secret by a configured run.
    written = _vaulted_pipeline(tmp_path / "written", secret=True)
    vault = tmp_path / "vault.bin"
    assert runner.invoke(app, ["run", str(written), "--vault", str(vault)]).exit_code == 0
    masked = tmp_path / "written" / "out.csv"

    no_secret = _vaulted_pipeline(tmp_path / "refused", secret=False)
    fpe_no_secret = _keyed_pipeline(tmp_path)
    argv, expected = {
        "run": (["run", str(fpe_no_secret)], guidance.RUN),
        "run --chunked": (["run", str(fpe_no_secret), "--chunked"], guidance.RUN),
        "run --vault": (["run", str(no_secret), "--vault", str(tmp_path / "v2.bin")], guidance.RUN),
        "unmask": (["unmask", str(fpe_no_secret), str(masked)], guidance.UNMASK),
        "unmask --vault": (
            ["unmask", str(no_secret), str(masked), "--vault", str(vault)],
            guidance.UNMASK,
        ),
        "report vault": (
            ["report", "vault", str(vault), "--config", str(no_secret)],
            guidance.REPORT_VAULT,
        ),
    }[route]
    result = runner.invoke(app, [*argv, "--json"])
    assert result.exit_code == EXIT_USAGE, result.output
    assert json.loads(result.stdout)["error"] == expected
