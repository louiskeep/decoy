"""A malformed `global_settings.mask_secret_ref` is refused without echoing it, on every surface.

The ref is a REFERENCE (`env:NAME` / `file:/PATH`); a user who pastes the secret itself, or a
list or number, into that slot must get a usage error (exit 1) that never repeats the value:
not on stdout or stderr, not in the JSON envelope, not in an exception message, not in a
traceback. `decoy run` and `decoy.mask()` pre-check the shape (DE-02); `decoy unmask`,
`decoy report vault` and `decoy tokenize` read the same slot and must refuse the same way.

A well-formed `vault://` ref is refused too: the CLI registers no Vault provider, so admission
fails with the constant `secret_provider_unknown` text, the ref is never echoed and nothing is
written. Characterization: it pins the V1 claim and asserts nothing about source-read order.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest
import yaml
from tests.csv_sources import csv_source
from tests.keyed_secret import TEST_MASK_SECRET_REF
from typer.testing import CliRunner

from decoy import _mask_secret_guidance as guidance
from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_USAGE

runner = CliRunner()

# Ordinary shapes a real secret takes: 64 hex chars, and a long integer.
CANARY_HEX = hashlib.sha256(b"decoy-ref-shape-canary").hexdigest()
CANARY_INT = 731946205831774029
_NEEDLES = (CANARY_HEX, CANARY_HEX[:16], CANARY_HEX[-16:], str(CANARY_INT), str(CANARY_INT)[:10])

_SHAPES: dict[str, object] = {
    "raw-secret-as-ref": {"seed": 42, "mask_secret_ref": CANARY_HEX},
    "ref-as-list": {"seed": 42, "mask_secret_ref": [CANARY_HEX]},
    "ref-as-number": {"seed": 42, "mask_secret_ref": CANARY_INT},
    "global-settings-null": None,
    "global-settings-list": [{"mask_secret_ref": CANARY_HEX}],
}


def _config(tmp_path: Path, global_settings: object) -> Path:
    src = tmp_path / "accounts.csv"
    pd.DataFrame({"ssn": ["123456789", "987654321", "111223333"]}).to_csv(src, index=False)
    cfg = {
        "version": 2,
        "global_settings": global_settings,
        "sources": {"accounts": csv_source(src)},
        "tables": [
            {
                "name": "accounts",
                "columns": [
                    {
                        "name": "ssn",
                        "strategy": "fpe",
                        "namespace": "ssn_ns",
                        "provider_config": {"charset": "digits"},
                        "vault": False,
                    }
                ],
            }
        ],
        "targets": {
            "accounts": {"type": "file", "format": "csv", "path": str(tmp_path / "out.csv")}
        },
    }
    path = tmp_path / "pipeline.yaml"
    path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return path


def _argv(command: str, cfg: Path, tmp_path: Path) -> list[str]:
    stub = tmp_path / "stub.bin"
    stub.write_bytes(b"not a real vault or masked file\n")
    return {
        "run": ["run", str(cfg)],
        "unmask": ["unmask", str(cfg), str(tmp_path / "accounts.csv")],
        "report vault": ["report", "vault", str(stub), "--config", str(cfg)],
        "tokenize": ["tokenize", str(cfg), "--vault", str(tmp_path / "tokens.db")],
    }[command]


def _assert_no_canary(text: str) -> None:
    for needle in _NEEDLES:
        assert needle not in text, f"canary fragment leaked: {text[:400]!r}"


@pytest.mark.parametrize("mode", ["console", "json", "verbose"])
@pytest.mark.parametrize("shape", sorted(_SHAPES))
@pytest.mark.parametrize("command", ["run", "unmask", "report vault", "tokenize"])
def test_malformed_ref_is_usage_and_never_echoed(
    tmp_path: Path, command: str, shape: str, mode: str
) -> None:
    cfg = _config(tmp_path, _SHAPES[shape])
    extra = {"console": [], "json": ["--json"], "verbose": ["--verbose"]}[mode]
    result = runner.invoke(app, [*_argv(command, cfg, tmp_path), *extra])
    everything = result.output + repr(result.exception)
    _assert_no_canary(everything)
    assert result.exit_code == EXIT_USAGE, (
        f"{command}/{shape}/{mode}: exit {result.exit_code}\n{result.output}"
    )
    if mode != "verbose":  # --verbose opts into the traceback; it is still canary-free above
        assert "Traceback" not in result.output
    if mode == "json":
        payload = json.loads(result.stdout)
        assert payload["status"] == "error"
    assert not (tmp_path / "out.csv").exists()
    assert not (tmp_path / "accounts.unmasked.csv").exists()


@pytest.mark.parametrize("shape", sorted(_SHAPES))
def test_mask_api_malformed_ref_raises_its_documented_error_without_echo(
    tmp_path: Path, shape: str
) -> None:
    from decoy.api import ConfigValidationError, MaskSecretConfigError, mask

    # `global_settings: null` is a schema error, the same one `decoy run` reports for it.
    expected = ConfigValidationError if shape == "global-settings-null" else MaskSecretConfigError
    with pytest.raises(expected) as info:
        mask(config=_config(tmp_path, _SHAPES[shape]))
    _assert_no_canary(str(info.value) + repr(info.value))
    assert info.value.__cause__ is None or not any(n in str(info.value.__cause__) for n in _NEEDLES)


VAULT_CANARY = f"decoy-vault-canary-{CANARY_HEX[:12]}"
VAULT_REF = f"vault://kv/{VAULT_CANARY}/app?version=3&field=key&encoding=hex"
_VAULT_SURFACES = ["run", "tokenize", "unmask", "report vault", "decoy.mask()"]


def _vault_cfg(d: Path, ref: str, strategy: str = "hash") -> Path:
    d.mkdir()
    src = d / "in.csv"
    pd.DataFrame({"email": ["a@x.com", "b@y.com", "a@x.com"]}).to_csv(src, index=False)
    col = {"name": "email", "strategy": strategy, "namespace": "em", "vault": strategy == "hash"}
    cfg = {
        "version": 2,
        "global_settings": {"seed": 42, "mask_secret_ref": ref},
        "sources": {"t": csv_source(src)},
        "tables": [{"name": "t", "columns": [col]}],
        "targets": {"t": {"type": "file", "format": "csv", "path": str(d / "out.csv")}},
    }
    (d / "pipeline.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return d / "pipeline.yaml"


def _tree(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.mark.usefixtures("mask_secret")
@pytest.mark.parametrize("surface", _VAULT_SURFACES)
def test_vault_ref_is_refused_without_echo(tmp_path: Path, surface: str) -> None:
    # Real inputs written under a valid secret, so the vault:// ref is the only fault left.
    good = _vault_cfg(tmp_path / "good", TEST_MASK_SECRET_REF)
    vault, masked = tmp_path / "good" / "vault.bin", tmp_path / "good" / "out.csv"
    made = runner.invoke(app, ["run", str(good), "--vault", str(vault)])
    assert made.exit_code == 0, made.output
    d = tmp_path / "v"
    cfg = _vault_cfg(d, VAULT_REF, "tokenize" if surface == "tokenize" else "hash")
    before = _tree(tmp_path)
    if surface == "decoy.mask()":
        from decoy.api import mask

        with pytest.raises(Exception) as info:
            mask(config=cfg)
        assert getattr(info.value, "code", None) == "secret_provider_unknown"
        _assert_no_canary(str(info.value) + repr(info.value))
        assert VAULT_CANARY not in str(info.value) + repr(info.value)
        assert _tree(tmp_path) == before
        return
    argv = {
        "run": ["run", str(cfg), "--vault", str(d / "vault.bin"), "--evidence-out", str(d / "e")],
        "tokenize": ["tokenize", str(cfg), "--vault", str(d / "tokens.db")],
        "unmask": ["unmask", str(cfg), str(masked), "--vault", str(vault), "-o", str(d / "p.csv")],
        "report vault": ["report", "vault", str(vault), "--config", str(cfg)],
    }[surface]
    remedy = guidance.SECRET_REMEDIES["secret_provider_unknown"]
    for extra in ([], ["--json"], ["--verbose"]):
        result = runner.invoke(app, [*argv, *extra])
        everything = result.output + repr(result.exception)
        assert VAULT_CANARY not in everything and "vault://" not in everything, everything[:400]
        assert result.exit_code == EXIT_USAGE, f"{surface}{extra}: {result.output}"
        if extra == ["--json"]:
            assert json.loads(result.stdout)["error"] == remedy
        else:
            assert " ".join(remedy.split()) in " ".join(result.output.split())
        assert _tree(tmp_path) == before, f"{surface}{extra} wrote or changed a file"
