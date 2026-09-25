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
    _match_extra,
    check_cloud_endpoints,
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
        assert _match_extra("cryptography") == "vault"

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


class TestTranslateMissingExtra:
    def test_translates_known_module_by_name_attribute(self) -> None:
        exc = ModuleNotFoundError("No module named 'boto3'", name="boto3")
        translated = translate_missing_extra(exc)
        assert translated is not None
        assert isinstance(translated, MissingExtraError)
        assert "pip install decoy-cli[cloud]" in str(translated)

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
