# Current executable scenario coverage

This table covers the main specifications in `openspec/specs/` plus the implemented, not-yet-archived `add-release-and-systemd-deployment` delta. `IMPLEMENTED_DELTAS` in `tests/test_verification_matrix.py` applies that delta and simulates synchronization in memory; the two new capabilities have no main specification until archival. Historical verification artifacts remain historical, and planning-only changes are excluded.

| Capability | Scenario | Executable tests |
| --- | --- | --- |
| questionnaires | Create from JSON | `tests/test_creation_api.py::test_json_creation_returns_only_absolute_url_and_expiry` |
| questionnaires | Create from YAML | `tests/test_creation_api.py::test_yaml_creation_has_the_same_questionnaire_structure` |
| questionnaires | Unsupported or malformed input | `tests/test_creation_api.py::test_unsupported_media_types_are_415_without_pushover` `tests/test_creation_api.py::test_malformed_bodies_are_400_without_pushover` |
| questionnaires | Create and follow to the stream | `tests/test_create_wait.py::test_sse_creation_returns_empty_relative_redirect` `tests/test_readme_curl.py::test_readme_curl_creates_waits_and_does_not_automatically_confirm` |
| questionnaires | SSE negotiation is explicit | `tests/test_create_wait.py::test_only_explicitly_preferred_sse_redirects` |
| questionnaires | SSE creation failure | `tests/test_create_wait.py::test_sse_creation_errors_do_not_redirect` `tests/test_create_wait.py::test_sse_creation_pushover_and_rate_limit_failures_keep_errors` |
| questionnaires | Redirect cannot change origin | `tests/test_create_wait.py::test_sse_creation_redirect_ignores_host_and_public_origin` |
| questionnaires | Waiting curl journey | `tests/test_readme_curl.py::test_readme_curl_creates_waits_and_does_not_automatically_confirm` |
| questionnaires | Answer wins the redirect race | `tests/test_readme_curl.py::test_readme_curl_fast_answer_uses_effective_url_for_confirmation` |
| questionnaires | Curl reports a creation error | `tests/test_readme_curl.py::test_readme_curl_creation_error_exits_nonzero_with_json` |
| questionnaires | Valid question types | `tests/test_models.py::test_valid_questions_receive_sequential_ids_and_preserve_options` `tests/test_models.py::test_optional_text_flags_accept_and_default_to_false` `tests/test_markdown_api.py::test_combined_yaml_polling_all_feedback_features` |
| questionnaires | Unsupported fields or values | `tests/test_models.py::test_unknown_question_fields` `tests/test_models.py::test_unsupported_question_types` `tests/test_models.py::test_optional_text_flags_require_booleans` |
| questionnaires | Oversized request body | `tests/test_creation_api.py::test_oversized_body_is_413_without_parsing_or_pushover` |
| questionnaires | Duplicate question name | `tests/test_creation_api.py::test_duplicate_question_name_has_no_creation_side_effects` |
| questionnaires | Names differing in case or whitespace | `tests/test_models.py::test_question_name_uniqueness_is_exact` |
| questionnaires | Malformed recipient key | `tests/test_creation_api.py::test_missing_or_invalid_recipient_is_400_without_pushover` |
| questionnaires | Pushover queues the notification | `tests/test_creation.py::test_acceptance_publishes_previously_invisible_pending_record` |
| questionnaires | Recipient opens a racing link | `tests/test_creation.py::test_acceptance_publishes_previously_invisible_pending_record` |
| questionnaires | Pushover rejects the recipient | `tests/test_creation.py::test_rejection_and_upstream_failure_delete_pending_and_map_errors` |
| questionnaires | Pushover outcome is unknown | `tests/test_creation.py::test_ambiguous_transport_failure_deletes_pending` |
| questionnaires | URL is the only credential | `tests/test_abuse_routes.py::test_omitted_allowlist_permits_unauthenticated_creation` `tests/test_retrieval_api.py::test_full_json_before_answering_has_ordered_questions_and_null_answers` |
| questionnaires | Unknown or deleted URL | `tests/test_retrieval_api.py::test_unknown_expired_and_confirmed_tokens_have_identical_404` |
| questionnaires | Multiple-question notification | `tests/test_pushover.py::test_notification_content_and_acceptance` |
| questionnaires | Pushover length limits | `tests/test_pushover.py::test_display_text_is_truncated_but_complete_url_is_preserved` |
| questionnaires | Render on a narrow screen | `tests/test_browser_forms.py::test_narrow_viewport_and_keyboard_submission` |
| questionnaires | Assets are self-contained | `tests/test_assets.py::test_browser_loads_only_same_origin_assets` |
| questionnaires | Incomplete or forged answers | `tests/test_submission_api.py::test_invalid_submissions_return_422_and_preserve_active_state` |
| questionnaires | Valid submission | `tests/test_submission_api.py::test_valid_htmx_submission_persists_arrays_and_returns_read_only_fragment` |
| questionnaires | Noncanonical indices | `tests/test_answers.py::test_noncanonical_or_out_of_range_index_is_rejected` |
| questionnaires | Text resembling an index | `tests/test_answers.py::test_numeric_option_text_is_not_an_index` |
| questionnaires | Validation preserves valid selections | `tests/test_browser_forms.py::test_narrow_viewport_and_keyboard_submission` `tests/test_templates.py::test_other_and_comment_controls_repopulate_validation_errors` |
| questionnaires | Concurrent submissions | `tests/test_submission_api.py::test_concurrent_submissions_have_exactly_one_winner` |
| questionnaires | Questionnaire already answered | `tests/test_submission_api.py::test_duplicate_submission_is_409_and_preserves_original_answers` |
| questionnaires | Poll before answering | `tests/test_retrieval_api.py::test_full_json_before_answering_has_ordered_questions_and_null_answers` `tests/test_recommendations.py::test_recommendations_match_full_polling_sse_and_restart` |
| questionnaires | Read after answering | `tests/test_retrieval_api.py::test_full_json_after_answering_is_complete_and_non_destructive` `tests/test_text_answers.py::test_rich_answers_are_consistent_across_full_polling_and_sse` |
| questionnaires | Answer is not ready | `tests/test_retrieval_api.py::test_answer_only_before_and_after_submission_is_repeatable` `tests/test_recommendations.py::test_recommendations_match_full_polling_sse_and_restart` |
| questionnaires | Answer is ready | `tests/test_retrieval_api.py::test_answer_only_before_and_after_submission_is_repeatable` `tests/test_recommendations.py::test_recommendations_match_full_polling_sse_and_restart` |
| questionnaires | Connect while awaiting an answer | `tests/test_sse.py::test_active_stream_has_immediate_status_and_transport_headers` |
| questionnaires | Stream transport protections | `tests/test_sse.py::test_active_stream_has_immediate_status_and_transport_headers` |
| questionnaires | Reconnect while waiting | `tests/test_sse.py::test_interrupted_stream_reconnects_to_current_answer_without_replay` |
| questionnaires | Answer arrives while connected | `tests/test_sse.py::test_answer_arrives_on_open_stream_and_closes_without_polling` |
| questionnaires | Answer predates the connection | `tests/test_sse.py::test_already_answered_stream_immediately_sends_answer_and_closes` |
| questionnaires | Questionnaire expires while connected | `tests/test_sse.py::test_expiry_is_terminal_and_later_connection_is_404` |
| questionnaires | Heartbeat proves liveness | `tests/test_sse.py::test_observable_heartbeat_arrives_on_schedule_and_stream_remains_open` |
| questionnaires | Interrupted stream reconnects | `tests/test_sse.py::test_interrupted_stream_reconnects_to_current_answer_without_replay` |
| questionnaires | Heartbeats do not extend retention | `tests/test_sse.py::test_heartbeats_do_not_extend_retention` |
| questionnaires | Confirm an answer | `tests/test_confirmation_api.py::test_successful_confirmation_deletes_and_repetition_is_generic_404` |
| questionnaires | Confirm too early or twice | `tests/test_confirmation_api.py::test_confirmation_before_answer_is_409_and_preserves_active_record` `tests/test_confirmation_api.py::test_successful_confirmation_deletes_and_repetition_is_generic_404` |
| questionnaires | Expire before or after answering | `tests/test_expiry.py::test_lazy_active_expiry_does_not_extend_on_reads` `tests/test_expiry.py::test_lazy_answered_expiry` |
| questionnaires | Cleanup without polling | `tests/test_expiry.py::test_cleanup_removes_active_and_answered_without_access` `tests/test_expiry.py::test_scheduler_cleans_without_access_and_starts_once` |
| questionnaires | Restart after answering | `tests/test_end_to_end.py::test_yaml_polling_journey_is_exact_and_non_destructive` `tests/test_readme_curl.py::test_rich_create_wait_restart_and_explicit_confirmation` |
| questionnaires | First submission fixes the answer timestamp | `tests/test_submission_api.py::test_concurrent_submissions_have_exactly_one_winner` `tests/test_text_answers.py::test_rich_competing_submissions_and_expiry` |
| questionnaires | Radio Other selection | `tests/test_answers.py::test_radio_other_is_separate_from_offered_answers` `tests/test_text_answers.py::test_rich_answers_are_consistent_across_full_polling_and_sse` |
| questionnaires | Checkbox Other selection | `tests/test_answers.py::test_checkbox_other_can_be_alone_or_with_offered_options` |
| questionnaires | Other needs a description | `tests/test_answers.py::test_selected_other_requires_nonempty_trimmed_text` |
| questionnaires | Disabled and repeated text fields | `tests/test_answers.py::test_text_fields_are_rejected_when_disabled_even_if_empty` `tests/test_answers.py::test_text_fields_reject_repeated_values` |
| questionnaires | Text field boundaries | `tests/test_answers.py::test_other_and_comment_use_unicode_code_point_limits` |
| questionnaires | Comment does not answer a question | `tests/test_answers.py::test_comment_does_not_replace_required_selection` `tests/test_templates.py::test_comment_alone_does_not_count_as_an_answer` |
| questionnaires | Plain text rendering | `tests/test_templates.py::test_answered_other_and_comment_are_escaped_and_preserve_lines` |
| questionnaires | Other and comment correction without scripts | `tests/test_browser_forms.py::test_no_javascript_other_error_preserves_text_and_succeeds_at_320px` |
| questionnaires | Text entry with HTMX | `tests/test_browser_forms.py::test_other_unicode_counter_and_comment_progress_at_320px` `tests/test_browser_forms.py::test_htmx_validation_and_success_use_fragments` |
| questionnaires | Separate creation and answer caps | `tests/test_answer_limits.py::test_answer_cap_is_independent_of_creation_cap` `tests/test_answer_limits.py::test_answer_cap_boundaries_for_urlencoded_and_multipart` `tests/test_answer_limits.py::test_confirmation_retains_creation_body_cap` |
| questionnaires | Aggregate Unicode body exceeds cap | `tests/test_answer_limits.py::test_worst_case_valid_unicode_fields_can_exceed_aggregate_cap` `tests/test_browser_forms.py::test_htmx_413_preserves_form_allows_retry_and_has_no_csp_errors` |
| questionnaires | Full-page oversized submission | `tests/test_answer_limits.py::test_full_page_413_is_understandable_and_does_not_echo_body` |
| questionnaires | Multiple recommendations | `tests/test_recommendations.py::test_recommendations_normalize_in_json_and_yaml` `tests/test_recommendations.py::test_recommendations_match_full_polling_sse_and_restart` `tests/test_readme_curl.py::test_rich_create_wait_restart_and_explicit_confirmation` |
| questionnaires | Invalid recommendation list | `tests/test_recommendations.py::test_invalid_recommendations_have_exact_field_and_no_side_effects` `tests/test_recommendations.py::test_yaml_rejects_noninteger_out_of_range_and_duplicate_recommendations` |
| questionnaires | Literal leading asterisks | `tests/test_recommendations.py::test_asterisks_and_backslashes_are_literal_not_recommendations` |
| questionnaires | Other cannot be recommended | `tests/test_recommendations.py::test_invalid_recommendations_have_exact_field_and_no_side_effects` |
| questionnaires | Initial recommendation presentation | `tests/test_recommendation_ui.py::test_initial_recommendations_are_accessible_guidance_without_preselection` |
| questionnaires | Recipient chooses freely | `tests/test_recommendation_ui.py::test_read_only_distinguishes_selected_and_not_chosen_recommendations` `tests/test_recommendation_ui.py::test_other_answer_does_not_hide_or_impersonate_recommendations` |
| questionnaires | Recommendations remain usable without JavaScript | `tests/test_recommendation_ui.py::test_recommendations_no_javascript_keyboard_and_correction` |
| questionnaires | Selected and unselected recommendations | `tests/test_recommendation_ui.py::test_read_only_distinguishes_selected_and_not_chosen_recommendations` |
| questionnaires | Other instead of a recommendation | `tests/test_recommendation_ui.py::test_other_answer_does_not_hide_or_impersonate_recommendations` |
| questionnaires | Option source length boundaries | `tests/test_markdown_api.py::test_markdown_option_source_boundaries` `tests/test_models.py::test_option_length_boundaries` |
| questionnaires | Code-first option | `tests/test_markdown_api.py::test_code_first_options_are_400_with_exact_field_and_no_side_effects` `tests/test_markdown.py::test_option_plain_text_first_and_code_first_validation` |
| questionnaires | Inline formatting in notification | `tests/test_pushover.py::test_inline_markdown_becomes_plain_text_without_changing_other_notification_fields` `tests/test_pushover.py::test_pushover_truncates_after_inline_conversion` |
| questionnaires | Supported inline formatting | `tests/test_markdown.py::test_supported_name_inline_formatting_and_plain_text` `tests/test_markdown_templates.py::test_active_markdown_has_safe_label_heads_and_associated_descriptions` |
| questionnaires | Unsupported and hostile syntax | `tests/test_markdown.py::test_unsupported_inline_and_block_syntax_is_literal_and_inert` `tests/test_markdown.py::test_raw_html_pair_preserves_nested_markdown_literally` `tests/test_markdown_browser.py::test_markdown_code_keyboard_selection_no_javascript_and_same_origin_requests` |
| questionnaires | Inline-only names | `tests/test_markdown.py::test_name_fences_and_indented_blocks_remain_inline_literal_text` |
| questionnaires | Plain-text answer fields | `tests/test_markdown_templates.py::test_other_comment_and_questioner_never_use_markdown_renderer` |
| questionnaires | Source fidelity and recommendation independence | `tests/test_markdown_api.py::test_markdown_source_fidelity_json_sse_restart_and_confirmation` `tests/test_recommendations.py::test_asterisks_and_backslashes_are_literal_not_recommendations` |
| questionnaires | Paragraph and code option | `tests/test_markdown.py::test_option_splits_head_paragraphs_breaks_and_code_without_user_attributes` `tests/test_markdown_templates.py::test_active_markdown_has_safe_label_heads_and_associated_descriptions` `tests/test_markdown_browser.py::test_markdown_code_keyboard_selection_no_javascript_and_same_origin_requests` |
| questionnaires | Narrow keyboard and no-JavaScript view | `tests/test_markdown_browser.py::test_markdown_code_keyboard_selection_no_javascript_and_same_origin_requests` |
| questionnaires | Answered rich option | `tests/test_markdown_templates.py::test_selected_and_not_chosen_options_retain_rich_formatting` `tests/test_markdown_api.py::test_markdown_source_fidelity_json_sse_restart_and_confirmation` |
| questionnaires | Invalid startup configuration | `tests/test_config.py::test_mandatory_fields` `tests/test_config.py::test_unknown_fields_are_errors` |
| questionnaires | Upstream failure is logged | `tests/test_security.py::test_upstream_diagnostic_log_is_actionable_without_secrets` |
| questionnaires | URL in status is not in answer data | `tests/test_security.py::test_security_headers_and_access_log_redaction_across_routes` |
| abuse-protection | No allowlist configured | `tests/test_abuse_routes.py::test_omitted_allowlist_permits_unauthenticated_creation` |
| abuse-protection | Label is not allowed | `tests/test_abuse_routes.py::test_case_or_whitespace_mismatch_is_forbidden_without_pushover` |
| abuse-protection | Empty allowlist | `tests/test_abuse_routes.py::test_explicitly_empty_allowlist_denies_every_label` |
| abuse-protection | Missing or blank label | `tests/test_creation_api.py::test_missing_or_invalid_questioner_is_400_without_pushover` |
| abuse-protection | Untrusted forwarding header | `tests/test_client_ip.py::test_spoofed_forwarding_header_from_untrusted_peer_is_ignored` |
| abuse-protection | Trusted reverse proxy | `tests/test_client_ip.py::test_trusted_ipv4_and_ipv6_proxies_supply_client` |
| abuse-protection | Sixth attempt in one window | `tests/test_abuse.py::test_first_five_attempts_are_allowed_and_sixth_is_limited` |
| abuse-protection | Invalid attempts consume quota | `tests/test_abuse_routes.py::test_invalid_creation_attempts_consume_route_quota` |
| abuse-protection | New window begins | `tests/test_abuse.py::test_rejected_attempts_do_not_extend_window_and_retry_after_is_exact` |
| abuse-protection | Client can schedule a retry | `tests/test_creation_api.py::test_sixth_creation_attempt_is_429_with_retry_after` |
| abuse-protection | Answer traffic is independent | `tests/test_abuse_routes.py::test_exhausted_creation_quota_does_not_affect_answer_traffic` |
| abuse-protection | First recipient rejection | `tests/test_abuse_integration.py::test_structured_recipient_rejection_integrates_with_backoff` |
| abuse-protection | Repeated recipient rejections | `tests/test_abuse.py::test_complete_recipient_backoff_schedule_and_cap` |
| abuse-protection | Other failures do not increase backoff | `tests/test_abuse_integration.py::test_excluded_pushover_response_failures_do_not_trigger_backoff` `tests/test_abuse_integration.py::test_network_failures_do_not_trigger_backoff` |
| abuse-protection | Wait elapses and delivery succeeds | `tests/test_abuse_integration.py::test_acceptance_resets_next_recipient_rejection_to_one_minute` |
| abuse-protection | Rate limit and backoff coincide | `tests/test_abuse.py::test_longer_backoff_delay_wins_when_rate_limit_also_applies` `tests/test_abuse.py::test_longer_rate_delay_wins_when_backoff_also_applies` |
| abuse-protection | Service restarts | `tests/test_abuse_routes.py::test_restart_resets_fixed_window_state` `tests/test_abuse_routes.py::test_restart_resets_recipient_backoff_state` |
| questionnaires | Public address with a path | `tests/test_review_contracts.py::test_public_address_with_path_is_rejected` `tests/test_review_contracts.py::test_public_address_at_root_is_accepted` |
| questionnaires | Deeply nested body | `tests/test_review_contracts.py::test_deeply_nested_body_is_a_client_error` `tests/test_review_contracts.py::test_deeply_nested_creation_returns_400_without_calling_pushover` |
| questionnaires | Unexpected server error | `tests/test_review_contracts.py::test_unexpected_errors_keep_the_json_error_contract` |
| questionnaires | Unreadable record is not served | `tests/test_unreadable_records.py::test_unreadable_records_return_the_generic_404_on_every_route` `tests/test_unreadable_records.py::test_unreadable_record_is_logged_once_without_its_token` |
| questionnaires | Unreadable record is deleted after its lifetime | `tests/test_unreadable_records.py::test_unreadable_record_is_deleted_by_cleanup_after_its_retention` `tests/test_unreadable_records.py::test_recovery_on_restart_deletes_unreadable_records_past_retention` |
| questionnaires | Validation errors receive focus | `tests/test_browser_swap_feedback.py::test_focus_moves_to_errors_then_to_the_stored_answer` `tests/test_accessibility.py::test_active_invalid_and_answered_states_have_no_wcag_violations` |
| questionnaires | Stored answer is announced | `tests/test_browser_swap_feedback.py::test_focus_moves_to_errors_then_to_the_stored_answer` `tests/test_accessibility.py::test_active_invalid_and_answered_states_have_no_wcag_violations` |
| questionnaires | Duplicate submission is dropped | `tests/test_browser_swap_feedback.py::test_duplicate_submissions_are_dropped_while_a_request_is_in_flight` `tests/test_browser_swap_feedback.py::test_htmx_configuration_disables_eval_and_script_tags` |
| questionnaires | Oversized API request receives JSON | `tests/test_review_contracts.py::test_only_the_browser_answer_form_receives_the_html_413_page` `tests/test_accessibility.py::test_request_too_large_page_has_no_wcag_violations` |
| abuse-protection | Rotating IPv6 addresses share one allowance | `tests/test_abuse_grouping.py::test_rotating_addresses_within_one_ipv6_64_share_the_creation_quota` `tests/test_abuse_grouping.py::test_recipient_backoff_applies_to_the_whole_ipv6_64` `tests/test_abuse_grouping.py::test_route_quota_is_shared_by_one_ipv6_64` |
| abuse-protection | Idle backoff state is forgotten | `tests/test_abuse_grouping.py::test_idle_backoff_state_expires_one_maximum_delay_after_the_block` `tests/test_abuse_grouping.py::test_rotating_rejected_clients_do_not_accumulate_backoff_state` `tests/test_readme_abuse.py::test_documented_client_grouping_and_backoff_expiry` |
| releases | Tag determines installed version | `tests/test_release_bundle.py::test_bundle_layout_and_version_injection` `tests/test_release_bundle.py::test_bundle_installs_without_source_writes` |
| releases | Invalid release tag | `tests/test_release_check.py::test_invalid_release_tags_are_rejected` |
| releases | Complete archive layout | `tests/test_release_bundle.py::test_bundle_layout_and_version_injection` |
| releases | Version injection preserves dependency pins | `tests/test_release_bundle.py::test_bundle_layout_and_version_injection` `tests/test_release_bundle.py::test_bundle_installs_without_source_writes` |
| releases | Failing gate blocks publication | `tests/test_release_workflow.py::test_all_gates_block_publication_and_dry_run_never_publishes` |
| releases | Exact archive is published | `tests/test_release_workflow.py::test_publish_uses_only_tested_archive_and_provenance` |
| releases | Re-running a published tag | `tests/test_release_workflow.py::test_existing_release_and_api_errors_block_release` |
| releases | Release candidate | `tests/test_release_check.py::test_cli_reports_release_candidate` `tests/test_release_workflow.py::test_publish_uses_only_tested_archive_and_provenance` |
| releases | Maintainer triggers release | `tests/test_release_check.py::test_source_placeholder_and_documented_tag` |
| linux-deployment | Install a release | `tests/test_deployment_e2e.py::test_manual_cold_start_and_permissions` |
| linux-deployment | First startup without a prepared environment | `tests/test_deployment_e2e.py::test_manual_cold_start_and_permissions` `tests/test_release_bundle.py::test_bundle_installs_without_source_writes` |
| linux-deployment | Restart uses prepared runtime | `tests/test_deployment_e2e.py::test_restart_preserves_records` |
| linux-deployment | Service starts at boot | `tests/test_deployment_e2e.py::test_service_one_worker_and_enabled` |
| linux-deployment | Invalid configuration | `tests/test_deployment_e2e.py::test_invalid_configuration_is_logged_and_limited` |
| linux-deployment | Application and configuration are read-only | `tests/test_deployment_e2e.py::test_sandbox_and_unit_validation` |
| linux-deployment | Unit passes validation | `tests/test_deployment_e2e.py::test_sandbox_and_unit_validation` |
| linux-deployment | Client address through Caddy | `tests/test_deployment_e2e.py::test_caddy_replaces_forged_headers` |
| linux-deployment | Answer stream through Caddy | `tests/test_deployment_e2e.py::test_caddy_streams_status_heartbeat_answer` |
| linux-deployment | Example configuration is valid | `tests/test_deployment_e2e.py::test_caddy_streams_status_heartbeat_answer` |
| linux-deployment | Reader follows the basic guide | `tests/test_deployment_files.py::test_installation_documents_fixed_version_and_restricted_files` |
