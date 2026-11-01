"""The one throwaway mask secret for tests that run keyed strategies.

Engine 0.17.0 refuses a keyed strategy (fpe, hash, date_shift, deterministic faker,
tokenize, vault) without an admitted mask secret, with no job_seed fallback. Tests hand it a
secret the way a user does: an `env:NAME` reference (YAML `global_settings.mask_secret_ref`,
`--mask-secret`, or `mask(mask_secret=)`) to a variable this module sets, so the real
admission path runs. The bytes are fixed and obviously fake; they must never appear in any
output, error, log or test id (tests/e2e/test_run_mask_secret.py asserts that).
"""

from __future__ import annotations

from typing import Any

import pytest

TEST_MASK_SECRET_ENV = "DECOY_TEST_MASK_SECRET"
TEST_MASK_SECRET_REF = f"env:{TEST_MASK_SECRET_ENV}"
# Hex text, the form `openssl rand -hex 32` gives a user; it decodes to 32 readable fake bytes.
TEST_MASK_SECRET_BYTES = b"decoy-test-only-throwaway-key-32"
TEST_MASK_SECRET = TEST_MASK_SECRET_BYTES.hex()
assert len(TEST_MASK_SECRET_BYTES) >= 32  # the engine's MIN_SECRET_BYTES floor


def secret_env() -> dict[str, str]:
    """The variable a child `decoy` process needs to resolve TEST_MASK_SECRET_REF."""
    return {TEST_MASK_SECRET_ENV: TEST_MASK_SECRET}


def with_mask_secret(cfg: dict[str, Any]) -> dict[str, Any]:
    """Point a pipeline dict's `global_settings.mask_secret_ref` at the test secret."""
    cfg.setdefault("global_settings", {})["mask_secret_ref"] = TEST_MASK_SECRET_REF
    return cfg


@pytest.fixture
def mask_secret(monkeypatch: pytest.MonkeyPatch) -> str:
    """Export the test secret for this test and return its `env:` reference."""
    monkeypatch.setenv(TEST_MASK_SECRET_ENV, TEST_MASK_SECRET)
    return TEST_MASK_SECRET_REF
