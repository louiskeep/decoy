"""Unit tests for decoy.cli.extras (CLI install DX, 2026-09-25).

Covers the pure logic of require_extra / translate_missing_extra /
_match_extra in isolation, without going through a full `decoy run`
invocation. See tests/e2e/test_run_missing_extras.py for the end-to-end
CLI-level behavior (exit codes, message shape) this logic feeds.
"""

from __future__ import annotations

import pytest

from decoy.cli.extras import (
    MissingExtraError,
    UnsupportedCloudEndpointError,
    _match_extra,
    check_cloud_endpoints,
    check_cloud_endpoints_supported,
    plan_compile_error_fields,
    require_extra,
    translate_missing_extra,
    translate_ner_unavailable,
)


class TestMatchExtra:
    def test_exact_top_level_match(self) -> None:
        assert _match_extra("spacy") == "ner"
        assert _match_extra("boto3") == "cloud"
        assert _match_extra("botocore") == "cloud"
        assert _match_extra("sklearn") == "ml"
        assert _match_extra("lightgbm") == "ml"

    def test_cryptography_is_not_mapped(self) -> None:
        # cryptography is a base engine dependency (FF1's
        # AES-256 backend), not optional -- vault is a pyproject-only
        # compatibility alias with no _MODULE_TO_EXTRA entry, so a real
        # cryptography import failure is never mislabeled as "install
        # [vault]" when it's actually a genuine broken install.
        assert _match_extra("cryptography") is None

    def test_dotted_prefix_match(self) -> None:
        # "google.cloud" is the registered key; a deeper submodule import
        # (as google-cloud-storage actually raises) must still match it.
        assert _match_extra("google.cloud.storage") == "cloud"
        assert _match_extra("google.cloud") == "cloud"

    def test_unknown_module_returns_none(self) -> None:
        assert _match_extra("numpy") is None
        assert _match_extra("google.ads") is None
        assert _match_extra("") is None


class TestRequireExtra:
    def test_importable_module_is_a_no_op(self) -> None:
        # `os` is always importable; require_extra must not raise even
        # though "os" isn't in the extras map (the map is only consulted
        # on failure).
        require_extra("os", why="this never fails")

    def test_missing_mapped_module_raises_missing_extra_error_with_install_line(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Route a guaranteed-absent module name through the real `ner`
        # extra so the test is deterministic regardless of whether spacy
        # itself happens to be installed in this dev/CI environment.
        import decoy.cli.extras as extras_mod

        monkeypatch.setitem(
            extras_mod._MODULE_TO_EXTRA, "decoy_cli_test_fixture_not_a_real_module", "ner"
        )
        with pytest.raises(MissingExtraError) as exc_info:
            require_extra("decoy_cli_test_fixture_not_a_real_module", why="PII autodetect (NER)")
        assert "pip install decoy-cli[ner]" in str(exc_info.value)
        assert "PII autodetect (NER)" in str(exc_info.value)

    def test_unmapped_missing_module_reraises_plain_import_error(self) -> None:
        with pytest.raises(ImportError):
            require_extra("decoy_cli_test_fixture_definitely_not_a_real_module", why="irrelevant")

    def test_extra_attribute_is_set_on_the_raised_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import decoy.cli.extras as extras_mod

        monkeypatch.setitem(
            extras_mod._MODULE_TO_EXTRA, "decoy_cli_test_fixture_not_a_real_module", "ner"
        )
        with pytest.raises(MissingExtraError) as exc_info:
            require_extra("decoy_cli_test_fixture_not_a_real_module", why="irrelevant")
        assert exc_info.value.extra == "ner"

    def test_unrelated_transitive_failure_is_not_mislabeled_as_missing_extra(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Probing "boto3" whose OWN import chain fails on some
        # unrelated missing module (a corrupted install, an ABI break) must
        # propagate the real error, not the "add [cloud]" fix -- installing
        # the extra again would not have helped.
        import decoy.cli.extras as extras_mod

        monkeypatch.setitem(extras_mod._MODULE_TO_EXTRA, "boto3", "cloud")

        def _fake_import(name: str) -> None:
            if name == "boto3":
                raise ModuleNotFoundError(
                    "No module named 'some_unrelated_transitive_dep'",
                    name="some_unrelated_transitive_dep",
                )
            raise AssertionError(f"unexpected import: {name}")

        monkeypatch.setattr("builtins.__import__", _fake_import)
        with pytest.raises(ModuleNotFoundError, match="some_unrelated_transitive_dep"):
            require_extra("boto3", why="irrelevant")

    def test_non_module_not_found_import_error_is_not_caught(self) -> None:
        # A plain ImportError (not ModuleNotFoundError -- e.g.
        # "cannot import name X from Y", a real defect) must propagate
        # unchanged; require_extra's except clause only catches
        # ModuleNotFoundError now.
        import decoy.cli.extras as extras_mod

        def _fake_import(name: str) -> None:
            raise ImportError("cannot import name 'X' from 'boto3' (a real defect)")

        import builtins

        original = builtins.__import__
        builtins.__import__ = _fake_import
        try:
            with pytest.raises(ImportError, match="a real defect"):
                require_extra("boto3", why="irrelevant")
        finally:
            builtins.__import__ = original
        del extras_mod  # imported only to document the module under test


class TestTranslateMissingExtra:
    def test_translates_known_module_by_name_attribute(self) -> None:
        exc = ModuleNotFoundError("No module named 'boto3'", name="boto3")
        translated = translate_missing_extra(exc)
        assert translated is not None
        assert isinstance(translated, MissingExtraError)
        assert "pip install decoy-cli[cloud]" in str(translated)
        assert translated.extra == "cloud"

    def test_translates_dotted_submodule_name(self) -> None:
        exc = ModuleNotFoundError(
            "No module named 'google.cloud.storage'", name="google.cloud.storage"
        )
        translated = translate_missing_extra(exc)
        assert translated is not None
        assert "pip install decoy-cli[cloud]" in str(translated)

    def test_translates_spacy_to_ner_extra(self) -> None:
        exc = ModuleNotFoundError("No module named 'spacy'", name="spacy")
        translated = translate_missing_extra(exc)
        assert translated is not None
        assert "pip install decoy-cli[ner]" in str(translated)

    def test_google_namespace_shell_absent_still_matches_cloud(self) -> None:
        # When the `google` namespace package itself is
        # entirely absent, Python reports exc.name == "google" (not the
        # full "google.cloud.storage" that was actually probed), which
        # doesn't match the "google.cloud" map key directly.
        exc = ModuleNotFoundError("No module named 'google'", name="google")
        translated = translate_missing_extra(exc)
        assert translated is not None
        assert "pip install decoy-cli[cloud]" in str(translated)

    def test_plain_import_error_is_not_module_not_found_returns_none(self) -> None:
        # Only ModuleNotFoundError is treated as a missing
        # extra now; any other ImportError (e.g. "cannot import name")
        # stays unclassified even if it happens to carry a matching .name.
        exc = ImportError("cannot import name 'client' from 'boto3'")
        exc.name = "boto3"  # some ImportError subclasses do set this
        assert translate_missing_extra(exc) is None

    def test_unmapped_module_returns_none(self) -> None:
        exc = ModuleNotFoundError("No module named 'numpy'", name="numpy")
        assert translate_missing_extra(exc) is None

    def test_import_error_without_name_returns_none(self) -> None:
        # Some ImportError call sites (rare, but real) never set `.name`.
        exc = ImportError("something went wrong")
        assert translate_missing_extra(exc) is None


class TestCheckCloudEndpoints:
    def test_local_file_sources_and_targets_are_a_no_op(self) -> None:
        check_cloud_endpoints(
            {
                "sources": {"accounts": {"type": "file", "format": "csv", "path": "x.csv"}},
                "targets": {"accounts": {"type": "file", "format": "csv", "path": "y.csv"}},
            }
        )

    def test_missing_sources_and_targets_keys_are_a_no_op(self) -> None:
        check_cloud_endpoints({})

    def test_cloud_source_without_extra_raises_missing_extra_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import decoy.cli.extras as extras_mod

        # Route "s3" through a guaranteed-absent module so the test is
        # deterministic regardless of whether boto3 happens to be installed
        # in this dev/CI environment.
        monkeypatch.setitem(
            extras_mod._CLOUD_ENDPOINT_MODULE, "s3", "decoy_cli_test_fixture_not_a_real_module"
        )
        monkeypatch.setitem(
            extras_mod._MODULE_TO_EXTRA, "decoy_cli_test_fixture_not_a_real_module", "cloud"
        )
        with pytest.raises(MissingExtraError) as exc_info:
            check_cloud_endpoints(
                {"sources": {"accounts": {"type": "s3", "bucket": "b", "key": "k"}}}
            )
        assert "pip install decoy-cli[cloud]" in str(exc_info.value)

    def test_cloud_target_is_also_checked(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import decoy.cli.extras as extras_mod

        monkeypatch.setitem(
            extras_mod._CLOUD_ENDPOINT_MODULE, "gcs", "decoy_cli_test_fixture_not_a_real_module"
        )
        monkeypatch.setitem(
            extras_mod._MODULE_TO_EXTRA, "decoy_cli_test_fixture_not_a_real_module", "cloud"
        )
        with pytest.raises(MissingExtraError):
            check_cloud_endpoints(
                {"targets": {"accounts": {"type": "gcs", "bucket": "b", "object": "o"}}}
            )


class TestCheckCloudEndpointsSupported:
    """`decoy run` cannot execute against s3/gcs at all yet,
    regardless of whether the SDK is installed -- this check fails closed
    unconditionally, distinct from check_cloud_endpoints's SDK-presence
    check above."""

    def test_local_file_sources_and_targets_are_a_no_op(self) -> None:
        check_cloud_endpoints_supported(
            {
                "sources": {"accounts": {"type": "file", "format": "csv", "path": "x.csv"}},
                "targets": {"accounts": {"type": "file", "format": "csv", "path": "y.csv"}},
            }
        )

    def test_missing_sources_and_targets_keys_are_a_no_op(self) -> None:
        check_cloud_endpoints_supported({})

    def test_s3_source_always_raises_regardless_of_sdk_presence(self) -> None:
        with pytest.raises(UnsupportedCloudEndpointError) as exc_info:
            check_cloud_endpoints_supported(
                {"sources": {"accounts": {"type": "s3", "bucket": "b", "key": "k"}}}
            )
        assert "s3" in str(exc_info.value)
        assert "accounts" in str(exc_info.value)
        assert "cannot run through" in str(exc_info.value)

    def test_gcs_target_also_raises(self) -> None:
        with pytest.raises(UnsupportedCloudEndpointError):
            check_cloud_endpoints_supported(
                {"targets": {"accounts": {"type": "gcs", "bucket": "b", "object": "o"}}}
            )


class TestTranslateNerUnavailable:
    def test_rewrites_spacy_not_installed_to_cli_extra(self) -> None:
        from decoy_engine.storm.ner import NerUnavailableError

        exc = NerUnavailableError(code="ner_spacy_not_installed", message="spaCy is not installed")
        translated = translate_ner_unavailable(exc)
        assert translated is not None
        assert "pip install decoy-cli[ner]" in str(translated)

    def test_leaves_model_not_installed_untranslated(self) -> None:
        # spaCy IS present here, just not the requested model -- the fix is
        # `spacy download <model>`, not an extra, so the engine's own
        # message should be left alone (translate_ner_unavailable -> None).
        from decoy_engine.storm.ner import NerUnavailableError

        exc = NerUnavailableError(code="ner_model_not_installed", message="model X missing")
        assert translate_ner_unavailable(exc) is None

    def test_non_ner_exception_returns_none(self) -> None:
        assert translate_ner_unavailable(ValueError("unrelated")) is None

    def test_rewrites_the_wrapped_plancompileerror_shape(self) -> None:
        # compile_plan wraps NerUnavailableError in
        # PlanCompileError(code=exc.code, ...) at plan-compile time, so a
        # real `decoy run`/`validate`/`preflight`/`plan` invocation never
        # sees a raw NerUnavailableError -- it arrives as this wrapped
        # shape. The unit test above (constructing NerUnavailableError
        # directly) is real coverage too, but this is the shape that
        # actually reaches the CLI; see tests/e2e/test_ner_missing_extra.py
        # for the full end-to-end proof through a real compile.
        from decoy_engine.plan import PlanCompileError

        exc = PlanCompileError(
            code="ner_spacy_not_installed",
            path="tables.customers.columns.notes.provider_config.ner",
            message="spaCy is not installed",
        )
        translated = translate_ner_unavailable(exc)
        assert translated is not None
        assert "pip install decoy-cli[ner]" in str(translated)
        assert translated.extra == "ner"

    def test_wrapped_plancompileerror_leaves_model_not_installed_untranslated(self) -> None:
        from decoy_engine.plan import PlanCompileError

        exc = PlanCompileError(
            code="ner_model_not_installed", path="tables.x.columns.y", message="model X missing"
        )
        assert translate_ner_unavailable(exc) is None


class TestPlanCompileErrorFields:
    """validate/preflight/plan each catch PlanCompileError and
    render exc.code/exc.message directly at their own call site; this is
    the shared boundary each routes through instead of duplicating the
    NER-rewrite check four times."""

    def test_ner_spacy_not_installed_is_rewritten(self) -> None:
        from decoy_engine.plan import PlanCompileError

        exc = PlanCompileError(
            code="ner_spacy_not_installed", path="tables.x.columns.y", message="spaCy missing"
        )
        code, message = plan_compile_error_fields(exc)
        assert code == "missing_extra"
        assert "pip install decoy-cli[ner]" in message
        # The [missing_extra] code prefix belongs to the
        # exception's __str__, not this rendered message -- callers already
        # display `code` and `message` as separate fields, so duplicating
        # the prefix into message would show it twice.
        assert "[missing_extra]" not in message

    def test_unrelated_code_passes_through_unchanged(self) -> None:
        from decoy_engine.plan import PlanCompileError

        exc = PlanCompileError(
            code="unknown_provider", path="tables.x.columns.y", message="no such provider"
        )
        code, message = plan_compile_error_fields(exc)
        assert code == "unknown_provider"
        assert message == "no such provider"
