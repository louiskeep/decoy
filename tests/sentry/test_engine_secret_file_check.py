"""The engine's own owner-only check on a `file:` mask secret reaches every CLI surface.

Engine 0.18.0 checks the mode with `fstat` on the descriptor it reads the secret from
(`runtime.secret_file_permissions_unsafe`). The CLI checks first (`decoy._mask_secret`) and hands
the engine that descriptor; here the mode is widened on the open descriptor right after the CLI's
check passes, so only the engine's check can refuse. Each surface must refuse with the CLI's
constant owner-only text, exit 1, and write nothing: the engine's refusal and the CLI's are one
route, not two texts.

POSIX only, like the check itself.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import pytest
from tests.sentry.test_mask_secret_file_mode import (
    _CLI_SURFACES,
    _NEEDS_VAULT,
    SOURCE,
    UNSAFE_TEXT,
    _api_config,
    _argv,
    _key,
    _masked_with_vault,
    _no_output,
    runner,
)

from decoy import _mask_secret
from decoy.__main__ import app
from decoy.cli.exit_codes import EXIT_USAGE

pytest.importorskip("cryptography")
pytestmark = pytest.mark.skipif(os.name == "nt", reason="the mode check is POSIX only")


def _widen_after_cli_check(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """From now on, widen the checked descriptor to 0644 once the CLI's own check passes."""
    real = _mask_secret._open_checked
    widened: list[int] = []

    def _checked_then_widened(locator: str) -> int:
        fd = real(locator)
        os.fchmod(fd, 0o644)
        widened.append(fd)
        return fd

    monkeypatch.setattr(_mask_secret, "_open_checked", _checked_then_widened)
    return widened


@pytest.mark.parametrize("surface", _CLI_SURFACES)
def test_engine_refuses_a_secret_widened_after_the_cli_check(
    tmp_path: Path, surface: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    written = _masked_with_vault(tmp_path / "w") if surface in _NEEDS_VAULT else None
    key = _key(tmp_path / "k" / "secret.key")
    root = tmp_path / "r"
    argv = _argv(surface, root, f"file:{key}", written)
    widened = _widen_after_cli_check(monkeypatch)
    result = runner.invoke(app, [*argv, "--json"])
    assert widened, "the CLI never checked the secret file"
    assert result.exit_code == EXIT_USAGE, result.output
    assert json.loads(result.stdout)["error"] == UNSAFE_TEXT
    assert "Traceback" not in result.output
    _no_output(root)


def test_api_mask_refuses_a_secret_widened_after_the_cli_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import decoy
    from decoy.api import MaskSecretConfigError

    key = _key(tmp_path / "secret.key")
    out = tmp_path / "out.csv"
    widened = _widen_after_cli_check(monkeypatch)
    with pytest.raises(MaskSecretConfigError) as caught:
        decoy.mask(pd.DataFrame({"email": SOURCE}), _api_config(f"file:{key}"), out=str(out))
    assert widened, "decoy.mask() never checked the secret file"
    assert str(caught.value) == UNSAFE_TEXT
    assert not out.exists()
