"""The closed vocabulary a CI finding's `rule_id` may carry.

`decoy ci` maps every upstream `.code` (the validation gate) and `.kind` (the evidence
verifier) through an allowlist instead of sanitising the string: a code that is not listed
here becomes `UNKNOWN_CODE`, so no upstream text -- a table name in a templated preflight
check, a future code that interpolates a value -- can reach JSON, SARIF or Markdown. This is
the SARIF `reportingDescriptor.id` contract (a stable rule identifier, not a message) applied
as an allow-list output encoding (OWASP ASVS V5.3: encode against a known-good set).

The sets are the codes the pinned engine, pydantic-core's `ErrorType`, the CLI gate and the
evidence verifier can produce today; `tests/unit/test_ci_rule_codes.py` re-derives them from
source and fails when upstream adds one, forcing an explicit decision here.
"""

from __future__ import annotations

import re

UNKNOWN_CODE = "unknown_code"

# Preflight names that embed the table name (`source.<table>.exists`). The table is user
# data, so only the fixed family token is emitted.
_TEMPLATED = re.compile(
    r"^(?P<family>source|target)\..+\."
    r"(?P<check>type|path|exists|is_file|readable|would_overwrite|parent_missing)$",
    re.DOTALL,
)
_TEMPLATED_CODES = frozenset(
    {
        "source.type", "source.path", "source.exists", "source.is_file", "source.readable",
        "target.would_overwrite", "target.parent_missing",
    }
)

_CLI_GATE_CODES: frozenset[str] = frozenset(
    {
        "capacity.out_of_core_fk", "capacity.source_unreadable", "compile_error",
        "compile_warning", "missing_extra", "native.companion", "native.eligibility",
        "no_profile_unique_incompatible", "pipeline.validation_error", "validation_error",
        "yaml.empty", "yaml.not_mapping", "yaml.parse_error",
    }
)

_PYDANTIC_ERROR_TYPES: frozenset[str] = frozenset(
    {
        "arguments_type", "assertion_error", "bool_parsing", "bool_type", "bytes_invalid_encoding",
        "bytes_too_long", "bytes_too_short", "bytes_type", "callable_type", "complex_str_parsing",
        "complex_type", "counter_type", "dataclass_exact_type", "dataclass_type",
        "date_from_datetime_inexact", "date_from_datetime_parsing", "date_future", "date_parsing",
        "date_past", "date_type", "datetime_from_date_parsing", "datetime_future",
        "datetime_object_invalid", "datetime_parsing", "datetime_past", "datetime_type",
        "decimal_max_digits", "decimal_max_places", "decimal_parsing", "decimal_type",
        "decimal_whole_digits", "default_factory_not_called", "deque_type", "dict_type",
        "ellipsis_error", "enum", "extra_forbidden", "finite_number", "float_parsing",
        "float_type", "fraction_parsing", "fraction_type", "frozen_dict_type", "frozen_field",
        "frozen_instance", "frozen_set_type", "get_attribute_error", "greater_than",
        "greater_than_equal", "int_from_float", "int_parsing", "int_parsing_size", "int_type",
        "invalid_key", "is_instance_of", "is_subclass_of", "iterable_type", "iteration_error",
        "json_invalid", "json_type", "less_than", "less_than_equal", "list_type", "literal_error",
        "mapping_type", "missing", "missing_argument", "missing_keyword_only_argument",
        "missing_positional_only_argument", "missing_sentinel_error", "model_attributes_type",
        "model_type", "multiple_argument_values", "multiple_of", "named_tuple_type",
        "needs_python_object", "no_such_attribute", "none_required", "ordered_dict_type",
        "recursion_loop", "set_item_not_hashable", "set_type", "string_not_ascii",
        "string_pattern_mismatch", "string_too_long", "string_too_short", "string_type",
        "string_unicode", "time_delta_parsing", "time_delta_type", "time_parsing", "time_type",
        "timezone_aware", "timezone_naive", "timezone_offset", "too_long", "too_short",
        "tuple_type", "unexpected_keyword_argument", "unexpected_positional_argument",
        "union_tag_invalid", "union_tag_not_found", "url_parsing", "url_scheme",
        "url_syntax_violation", "url_too_long", "url_type", "uuid_parsing", "uuid_type",
        "uuid_version", "value_error",
    }
)

_ENGINE_CODES: frozenset[str] = frozenset(
    {
        "abi-mismatch", "absent", "allow_collisions_mode_conflict", "ambiguous_name",
        "bad_secret_ref", "batch_deterministic_unsupported", "blocklist_exhausted",
        "bucket_perturb_date_format_unsupported", "bucket_perturb_invalid_config",
        "bucket_perturb_preserve_values_invalid", "bucket_perturb_requires_namespace",
        "bucket_perturb_unrecognized_bucket", "bucketize_width_unresolvable",
        "bundle_missing_output_columns", "capability_violation", "capacity_source_unprofilable",
        "cardinality_match_deviation", "cardinality_target_exceeds_pool", "catalog_read_failed",
        "categorical_categories_missing", "categorical_categories_not_list",
        "categorical_nondeterministic_not_chunk_safe", "categorical_position_out_of_domain",
        "categorical_requires_categories", "categorical_requires_namespace",
        "categorical_weight_below_resolution", "categorical_weights_negative",
        "categorical_weights_nonpositive", "categorical_weights_shape",
        "chunked_bucket_perturb_fk_key_unsupported",
        "chunked_bucket_perturb_source_dtype_unsupported",
        "chunked_bucket_perturb_when_not_supported",
        "chunked_categorical_nondeterministic_when_not_supported",
        "chunked_code_set_fk_key_unsupported", "chunked_code_set_source_dtype_unsupported",
        "chunked_code_set_when_not_supported", "chunked_faker_deterministic_pool_not_string",
        "chunked_faker_nondeterministic_pool_not_string",
        "chunked_faker_nondeterministic_when_not_supported", "chunked_fk_child_config_mismatch",
        "chunked_fk_child_key_dtype_mismatch", "chunked_fk_child_key_dtype_unprovable",
        "chunked_fk_child_namespace_mismatch", "chunked_fk_child_namespace_missing",
        "chunked_fk_child_strategy_mismatch", "chunked_fk_child_strategy_missing",
        "chunked_fk_child_when_unsupported", "chunked_fk_composite_unsupported",
        "chunked_fk_declared_dtype_mismatch", "chunked_fk_endpoint_not_scalar",
        "chunked_fk_key_dtype_not_cross_adapter_safe", "chunked_fk_orphan_policy_not_remap",
        "chunked_fk_parent_namespace_mismatch", "chunked_fk_parent_namespace_missing",
        "chunked_fk_parent_not_root", "chunked_fk_parent_strategy_not_self_mask_safe",
        "chunked_fk_parent_when_unsupported", "chunked_generate_unsupported",
        "chunked_group_key_group_by_dtype_unsupported", "chunked_group_key_when_not_supported",
        "chunked_leading_null_type", "chunked_passthrough_value_unrepresentable",
        "chunked_route_evidence_inconsistent", "chunked_route_evidence_mixed_tables",
        "chunked_row_offset_out_of_domain", "chunked_schema_mismatch",
        "chunked_strategy_conditions_unmet", "chunked_table_unknown",
        "chunked_text_mask_source_dtype_unsupported", "chunked_text_mask_when_not_supported",
        "chunked_windowed_date_when_not_supported", "code_set_chapter_absent",
        "code_set_chapter_column_missing", "code_set_corpus_duplicate_codes",
        "code_set_corpus_empty", "code_set_corpus_empty_code",
        "code_set_corpus_incoherent_chapter", "code_set_corpus_missing_code_column",
        "code_set_corpus_missing_provenance", "code_set_corpus_not_found",
        "code_set_corpus_null_code", "code_set_corpus_path_not_found",
        "code_set_corpus_provenance_identity_mismatch",
        "code_set_corpus_provenance_malformed_stamp", "code_set_corpus_read_error",
        "code_set_corpus_source_version_invalid", "code_set_corpus_version_mismatch",
        "code_set_gen_requires_namespace", "code_set_name_missing",
        "code_set_reserved_licensed_name", "code_set_single_row_corpus",
        "code_set_sole_member_bucket", "collision_rate", "column_not_found",
        "composite_columns_length_mismatch", "composite_custom_bundle_item_missing_keys",
        "composite_custom_bundle_item_shape", "composite_custom_bundle_shape",
        "composite_custom_bundle_size", "composite_custom_duplicate_columns",
        "composite_custom_no_nesting", "composite_fk_group_no_edge",
        "composite_namespace_unresolved", "composite_output_column_missing",
        "composite_requires_bundle_path", "composite_wiring_inconsistent",
        "config_references_stored_index", "cyclic_work_ordering",
        "date_preserve_values_unsupported_fk_shape",
        "date_preserve_values_with_group_by_unsupported",
        "date_shift_group_anchor_snapshot_misaligned", "date_shift_group_anchor_snapshot_missing",
        "date_shift_group_by_on_fk_column_unsupported",
        "date_shift_group_by_unsupported_in_nested", "date_shift_group_by_with_when_unsupported",
        "date_shift_invalid_config", "date_shift_missing_group_by_ref",
        "date_shift_preserve_values_invalid", "date_shift_requires_namespace", "deadline_exceeded",
        "dedupe_column_missing", "dedupe_unsupported_type", "derive_column_already_exists",
        "derive_expression_error", "derive_result_not_convertible",
        "derived_aggregate_column_missing", "derived_aggregate_missing_column_ref",
        "derived_aggregate_op_invalid", "derived_aggregate_op_missing", "derived_bounds_invalid",
        "derived_bounds_inverted", "derived_cyclic_reference", "derived_expression_missing",
        "derived_missing_column_ref", "derived_null_propagation_invalid",
        "deterministic_mode_unsupported_cardinality", "deterministic_namespace_missing",
        "deterministic_requires_namespace_and_seed", "deterministic_requires_source_and_namespace",
        "deterministic_requires_source_and_seed", "deterministic_requires_source_value",
        "dp_adapter_ambiguous_column", "dp_adapter_duplicate_column", "dp_adapter_missing_column",
        "dp_adapter_source_type", "dp_budget_categorical_pair_unscheduled",
        "dp_budget_declaration_malformed", "dp_budget_exceeded", "dp_budget_infeasible",
        "dp_carrier_backend_unsupported", "dp_carrier_bounds_missing",
        "dp_carrier_bounds_nonfinite", "dp_carrier_bounds_order", "dp_carrier_bounds_type",
        "dp_carrier_flag_dtype", "dp_carrier_flag_length", "dp_carrier_invalid",
        "dp_carrier_number_dtype", "dp_carrier_number_length", "dp_carrier_row_count_negative",
        "dp_carrier_row_count_type", "dp_carrier_schema_mismatch", "dp_carrier_text_shape",
        "dp_carrier_type_mismatch", "dp_carrier_unknown", "dp_carrier_validity_length",
        "dp_carrier_validity_shape", "dp_delta_invalid", "dp_duplicate_release",
        "dp_epsilon_invalid", "dp_epsilon_unsupported", "dp_flag_token_invalid",
        "dp_generate_allow_real_categories_unsupported",
        "dp_generate_high_cardinality_unsupported", "dp_joint_unsupported",
        "dp_kind_carrier_mismatch", "dp_kind_unknown", "dp_lock_installed_mismatch",
        "dp_lock_parse_error", "dp_numeric_bins_invalid", "dp_numeric_domain_invalid",
        "dp_pinned_snapshot_digest_mismatch", "dp_pinned_snapshot_payload_not_json",
        "dp_platform_uncertified", "dp_provenance_distribution_unnamed",
        "dp_provenance_duplicate_distribution", "dp_provenance_record_malformed",
        "dp_schedule_incomplete", "dp_schedule_mismatch", "dp_schema_column_type",
        "dp_schema_type", "dp_snapshot_codec_unsupported",
        "dp_snapshot_embedded_artifact_too_large", "dp_snapshot_numeric_edges_mismatch",
        "dp_snapshot_numeric_shape_mismatch", "dp_snapshot_release_shape_unsupported",
        "dp_stack_uncertified", "dp_unscheduled_release", "drop_column_missing",
        "duckdb_unavailable", "duplicate_relation", "duplicate_source_field_names",
        "empty_domain_pool", "empty_locality_table", "exact_int_null_mask_mismatch",
        "export_failed", "extension_unavailable", "extension_untrusted_location",
        "faker_position_out_of_domain", "faker_positional_table_unknown",
        "faker_requires_provider", "field_missing", "filter_expression_error",
        "filter_expression_not_boolean", "fk_cycle", "fk_full_frame_oom_risk_rejected",
        "fk_full_frame_oom_risk_rejected_estimated", "float_canonicalization_unsupported",
        "format_rule_violation", "fpe.checksum_invalid_source", "fpe.unencryptable_domain",
        "fpe.unencryptable_length", "fpe_charset_degenerate", "fpe_charset_duplicate_symbols",
        "fpe_charset_non_ascii", "fpe_checksum_charset_incompatible",
        "fpe_checksum_iban_unsupported", "fpe_checksum_invalid_source",
        "fpe_checksum_unknown_scheme", "fpe_join_group_active", "fpe_join_group_config_mismatch",
        "fpe_join_group_namespace_mismatch", "fpe_join_group_non_fpe_member",
        "fpe_join_group_singleton", "fpe_partial_plaintext_disclosure", "fpe_requires_namespace",
        "fpe_unencryptable_domain", "fpe_unencryptable_length", "full_frame_value_unrepresentable",
        "gated_hash_on_integer_unsupported", "gated_string_output_on_numeric_unsupported",
        "generation_budget_exceeded", "generation_column_unbounded", "geo_generalize_cascade",
        "geo_generalize_invalid_cascade", "geo_generalize_invalid_cascade_level",
        "geo_generalize_missing_suppress", "geo_generalize_unsupported_type",
        "group_key_group_by_missing", "group_key_length_odd", "group_key_length_out_of_range",
        "group_key_missing_group_by_ref", "grouped_series_generator_invalid",
        "grouped_series_group_by_missing", "grouped_series_missing_group_by_ref",
        "grouped_series_missing_order_by_ref", "grouped_series_order_by_missing",
        "grouped_series_step_out_of_range", "hash_requires_namespace",
        "high_cardinality_ambiguous_string_coercion", "high_cardinality_columns_not_collection",
        "high_cardinality_distinct_limit_exceeded", "high_cardinality_invalid_label_encoding",
        "high_cardinality_label_bytes_limit_exceeded", "high_cardinality_non_string_dtype",
        "hold_back_spill_unavailable", "index_batch_length_mismatch",
        "index_batch_null_mask_mismatch", "index_batch_out_of_bounds", "index_batch_type_mismatch",
        "internal_publish_not_committed", "invalid_cusip_char", "invalid_execution_knob",
        "invalid_input_length", "invalid_native_threads", "invalid_seed_length",
        "invalid_substrate", "joint_mask_column_not_in_reference", "joint_mask_columns_missing",
        "joint_mask_key_by_missing", "joint_mask_key_by_snapshot_misaligned",
        "joint_mask_key_by_snapshot_missing", "joint_mask_reference_invalid",
        "joint_mask_reference_missing", "joint_mask_reference_not_found", "kat-corrupt",
        "keyed_strategy_requires_secret", "lazy_source_changed", "lazy_source_row_count_mismatch",
        "load-error", "measured", "mimesis_locale_fallback", "missing_mask_secret",
        "missing_namespace", "missing_seed", "mixed_key_payload_misaligned",
        "multi_table_result_has_no_single_output", "namespace_ambiguity", "namespace_empty",
        "namespace_missing", "native_chunk_schema_drift", "native_type_not_admitted",
        "ner_model_not_installed", "ner_model_version_mismatch", "ner_spacy_not_installed",
        "nested_cell_json_parse_error", "nested_child_row_error_unmappable",
        "nested_child_strategy_unknown", "nested_jsonpath_parse_error",
        "nested_jsonpath_path_overlap", "nested_recursive_nested_rejected",
        "nested_strategy_unset", "nested_target_matched_nothing", "nested_target_unset",
        "nested_target_unwritable_container", "no_native_bucket_calls",
        "no_native_date_shift_calls", "no_selections", "non_poolable_provider_with_pool_backend",
        "null_bearing_int_unsupported", "null_canonicalization_unreachable", "numexpr_required",
        "orphan_fk", "orphan_fk_policy_duplicate", "orphan_fk_policy_invalid",
        "orphan_fk_policy_missing", "orphan_fk_violation", "orphan_policy_conflict",
        "orphan_remap_parent_missing", "out_of_core_backend_unavailable",
        "out_of_core_batch_rows_invalid", "out_of_core_bucket_perturb_autodetect_unsupported",
        "out_of_core_bucket_perturb_column_missing",
        "out_of_core_bucket_perturb_source_type_drift", "out_of_core_budget_invalid",
        "out_of_core_caller_managed_residency", "out_of_core_categorical_column_missing",
        "out_of_core_categorical_nondeterministic_unsupported",
        "out_of_core_categorical_source_type_drift", "out_of_core_categorical_unprepared",
        "out_of_core_child_column_missing", "out_of_core_child_key_types_mismatch",
        "out_of_core_code_set_row_error_unreachable", "out_of_core_code_set_shape_unsupported",
        "out_of_core_concurrency_invalid", "out_of_core_faker_column_missing",
        "out_of_core_faker_index_unavailable", "out_of_core_faker_pool_budget_exceeded",
        "out_of_core_faker_pool_budget_invalid", "out_of_core_faker_pool_size_invalid",
        "out_of_core_faker_pool_unsupported", "out_of_core_faker_source_type_drift",
        "out_of_core_faker_source_type_unsupported", "out_of_core_faker_unprepared",
        "out_of_core_fanin_exceeds_budget", "out_of_core_fk_join_plan_unverified",
        "out_of_core_fk_key_dtype_unsupported", "out_of_core_fk_reorder_contiguity",
        "out_of_core_fk_row_alignment", "out_of_core_fpe_column_missing",
        "out_of_core_fpe_column_required", "out_of_core_fpe_native_result_invalid",
        "out_of_core_fpe_source_type_drift", "out_of_core_fpe_unprepared",
        "out_of_core_hash_column_missing", "out_of_core_hash_input_type_drift",
        "out_of_core_hash_native_result_invalid", "out_of_core_insufficient_memory",
        "out_of_core_memory_detection_failed", "out_of_core_parent_column_missing",
        "out_of_core_parent_rows_unresolved", "out_of_core_parent_seed_missing",
        "out_of_core_parent_strategy_unsupported", "out_of_core_predicted_spill_bytes_invalid",
        "out_of_core_rejected", "out_of_core_relationship_cycle",
        "out_of_core_remap_seeds_missing", "out_of_core_remap_values_missing",
        "out_of_core_reorder_budget_too_small", "out_of_core_reorder_disk_budget_invalid",
        "out_of_core_reorder_fan_in_invalid", "out_of_core_reorder_head_fit_invalid",
        "out_of_core_reorder_threshold_invalid", "out_of_core_reorder_unbudgeted",
        "out_of_core_reserved_bytes_invalid", "out_of_core_sort_invalid_state",
        "out_of_core_sort_key_missing", "out_of_core_sort_key_null",
        "out_of_core_sort_key_type_drift", "out_of_core_sort_key_type_unsupported",
        "out_of_core_sort_row_index_unbounded", "out_of_core_sort_row_too_wide",
        "out_of_core_sorter_schema_not_slim", "out_of_core_source_missing",
        "out_of_core_source_schema_required", "out_of_core_strategy_unsupported",
        "out_of_core_temp_disk_exceeded", "out_of_core_text_mask_column_missing",
        "out_of_core_text_mask_native_result_invalid", "out_of_core_text_mask_source_type_drift",
        "out_of_core_text_mask_unprepared", "out_of_core_text_redact_column_missing",
        "out_of_core_text_redact_native_result_invalid",
        "out_of_core_text_redact_source_type_drift", "out_of_core_text_redact_unprepared",
        "out_of_core_validators_not_admitted", "out_of_core_vault_config_required",
        "pinned_determinism_fresh", "pinned_live_token", "pinned_not_generation_only",
        "pinned_plan_malformed", "pinned_reference_date_invalid", "pinned_runtime_changed",
        "pinned_seed_invalid", "pinned_snapshot_file_not_statistical",
        "pinned_statistical_digest_missing", "pinned_type_not_allowlisted",
        "pinned_windowed_anchor_not_absolute", "plan_schema_deterministic_map_renamed",
        "pool_capacity_pre_flight_unique", "pool_capacity_unverifiable_no_profile",
        "pool_dominates_cache", "pool_duplicate_rate", "pool_exceeds_cache_budget",
        "pool_size_invalid", "pool_size_location_conflict", "pool_size_overflow",
        "pool_too_small_for_source", "present-ok", "process_exited", "provider_not_poolable",
        "raw_hex_batch_length_mismatch", "raw_hex_batch_type_mismatch",
        "raw_hex_batch_unexpected_null", "read_error", "relation_not_found", "relationship_cycle",
        "run_single_requires_table", "scan_crashed", "seed_not_numeric", "seed_overflow",
        "seed_wrong_length", "sequential_composite_fk_chain_unsupported",
        "sequential_fpe_key_integer_not_preserved", "sequential_fpe_native_result_invalid",
        "shuffle_requires_namespace", "site_not_partitionable", "site_not_reproducible",
        "sort_ascending_length_mismatch", "sort_column_missing", "sort_unsupported_type",
        "source_length_mismatch", "source_required_for_cardinality_mode", "source_unreachable",
        "source_value_leak", "split_sink_needs_all_dispatched",
        "statistical_allow_real_categories_invalid_type", "statistical_column_not_in_snapshot",
        "statistical_condition_column_unavailable", "statistical_condition_kind_invalid",
        "statistical_dp_carrier_invalid", "statistical_flag_other_mode_emit_invalid",
        "statistical_flag_requires_dp_declaration", "statistical_flag_token_invalid",
        "statistical_high_cardinality_invalid_type", "statistical_high_cardinality_kind_invalid",
        "statistical_high_cardinality_requires_real_categories",
        "statistical_high_cardinality_snapshot_mismatch",
        "statistical_high_cardinality_wrong_type", "statistical_joint_missing",
        "statistical_kind_unsupported", "statistical_other_mode_invalid",
        "statistical_real_categories_not_allowed", "statistical_snapshot_file_required",
        "statistical_snapshot_index_out_of_range", "statistical_snapshot_not_pinned",
        "statistical_snapshot_schema_mismatch", "statistical_snapshot_unreadable",
        "statistical_spec_not_pinned", "statistical_stats_degenerate", "stopped",
        "strategy_not_chunk_safe", "subset_budget_exceeded", "subset_closure_invariant_violated",
        "subset_closure_nontermination", "subset_config_missing",
        "subset_dangling_not_acknowledged", "subset_duplicate_seed_table",
        "subset_materialize_count_mismatch", "subset_output_dir_exists",
        "subset_relationship_column_missing", "subset_relationship_composite_length",
        "subset_relationship_duplicate_column", "subset_relationship_key_float_unsupported",
        "subset_relationship_type_mismatch", "subset_requires_parquet", "subset_reserved_column",
        "subset_seed_key_type", "subset_seed_key_uncanonicalizable", "subset_source_orphans",
        "subset_source_type_unsupported", "subset_unknown_edge", "subset_unknown_table",
        "text_mask_sub_floor_span_handled", "thread_start_failed", "timezone_naive_datetime",
        "tokenize_requires_namespace", "tokenize_requires_string_dtype", "tokenize_requires_vault",
        "tokenize_vault_error", "top_code_bounds_unresolvable", "top_code_floor_ge_cap",
        "top_code_generalized", "top_code_invalid_floor", "top_code_missing_over_label",
        "top_code_missing_under_label", "top_code_non_integral_object_column",
        "top_code_under_label_without_floor", "top_code_unsupported_in_nested",
        "top_code_with_when_unsupported", "transform_lineage_mismatch", "transform_source_missing",
        "truncate_keep_invalid", "truncate_length_invalid", "truncate_mask_char_invalid",
        "undeclared_output_columns", "uniqueness_impossible", "unknown_cardinality_mode",
        "unknown_composite", "unknown_provider", "unknown_transform_op", "unsupported_column_type",
        "unsupported_locale", "unsupported_strategy", "value_exceeds_declared_bound",
        "value_guard_failed", "value_not_representable", "value_reuse_fixed_point",
        "vault_crypto_not_installed", "vault_format_unsupported", "vault_key_mismatch",
        "vault_protocol_version_mismatch", "vault_requires_cryptography",
        "vault_requires_namespace", "vault_strategy_reversible", "vault_strategy_unmasked",
        "vault_unreadable", "vault_writer_unsupported", "weak_mask_secret",
        "when_expression_error", "when_expression_not_boolean", "when_outside_closed_grammar",
        "when_predicate_not_native", "when_predicate_outside_native_subset",
        "when_predicate_reads_masked_column", "when_string_output_on_numeric_unsupported",
        "when_with_coherent_with_unsupported", "windowed_date_anchor_missing",
        "windowed_date_distribution_invalid", "windowed_date_max_days_missing",
        "windowed_date_min_exceeds_max", "windowed_date_missing_anchor_ref",
        "windowed_date_position_out_of_domain",
    }
)

EVIDENCE_KINDS: frozenset[str] = frozenset(
    {
        "input_fingerprint_changed", "input_missing", "manifest_hash_mismatch",
        "output_fingerprint_changed", "output_missing", "pipeline_fingerprint_changed",
        "pipeline_missing",
    }
)

VALIDATION_CODES: frozenset[str] = (
    _CLI_GATE_CODES | _PYDANTIC_ERROR_TYPES | _ENGINE_CODES | _TEMPLATED_CODES
)


def rule_code(code: object, allowed: frozenset[str]) -> str:
    """`code` itself when allowlisted, its family token when templated, else UNKNOWN_CODE."""
    if not isinstance(code, str):
        return UNKNOWN_CODE
    if code in allowed:
        return code
    match = _TEMPLATED.match(code)
    if match is not None:
        family = f"{match['family']}.{match['check']}"
        if family in allowed:
            return family
    return UNKNOWN_CODE


__all__ = ["EVIDENCE_KINDS", "UNKNOWN_CODE", "VALIDATION_CODES", "rule_code"]
