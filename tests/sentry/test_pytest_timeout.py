"""A hung test must fail with a stack dump, not stall the suite.

pytest-timeout is a dev dependency; ``[tool.pytest.ini_options]`` sets the per-test default.
This sentry fails if the plugin is not loaded or the default is missing or zero, and a subprocess
run proves a test that outlives its timeout fails with "Timeout" and its stack in the output.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[2]


def configured_timeout(pyproject_text: str) -> float:
    """The default per-test timeout in seconds, or 0 when none is configured."""
    ini = tomllib.loads(pyproject_text)["tool"]["pytest"]["ini_options"]
    return float(ini.get("timeout", 0))


def test_plugin_is_loaded(pytestconfig: pytest.Config) -> None:
    assert pytestconfig.pluginmanager.hasplugin("timeout"), (
        "pytest-timeout is not loaded: install the dev extra (pip install -e '.[dev]')"
    )


def test_default_timeout_is_configured_and_positive(pytestconfig: pytest.Config) -> None:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert configured_timeout(text) > 0, "pyproject.toml sets no `timeout` under pytest ini_options"
    assert float(pytestconfig.getini("timeout")) > 0, "the effective pytest timeout is zero"


def test_missing_setting_is_detected() -> None:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    stripped = "\n".join(ln for ln in text.splitlines() if not ln.startswith("timeout = "))
    assert configured_timeout(stripped) == 0
    assert (
        configured_timeout(
            stripped.replace("[tool.pytest.ini_options]", "[tool.pytest.ini_options]\ntimeout = 0")
        )
        == 0
    )


def test_a_test_past_its_timeout_fails_with_a_stack(tmp_path: Path) -> None:
    (tmp_path / "test_hang.py").write_text(
        "import time\n\n\ndef test_hangs():\n    time.sleep(30)\n", encoding="utf-8"
    )
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "--timeout=1", "-q",
         "--rootdir", str(tmp_path), "-c", "/dev/null" if sys.platform != "win32" else "NUL",
         str(tmp_path / "test_hang.py")],
        capture_output=True, text=True, timeout=60, cwd=tmp_path, check=False,
    )  # fmt: skip
    out = proc.stdout + proc.stderr
    assert proc.returncode == 1, out
    assert "Timeout" in out, out
    assert "test_hang.py" in out and "time.sleep(30)" in out, out
