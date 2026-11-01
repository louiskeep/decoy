"""A malformed `global_settings.mask_secret_ref` is refused without echoing it, on every surface.

The ref is a REFERENCE (`env:NAME` / `file:/PATH`); a user who pastes the secret itself, or a
list or number, into that slot must get a usage error (exit 1) that never repeats the value:
not on stdout or stderr, not in the JSON envelope, not in an exception message, not in a
traceback. `decoy run` and `decoy.mask()` pre-check the shape (DE-02); `decoy unmask`,
`decoy report vault` and `decoy tokenize` read the same slot and must refuse the same way.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

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
        "sources": {"accounts": {"type": "file", "format": "csv", "path": str(src)}},
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
