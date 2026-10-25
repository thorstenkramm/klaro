# Verification matrix

Every specification scenario has automated coverage. Browser scenarios use Playwright with real Chromium; there are no manual-only exceptions. The consistency check in `tests/test_verification_matrix.py` compares this table with the scenario headings and validates every referenced test node.

Run the complete gate with:

```shell
uv sync --frozen
uv run pytest
uv run ruff check .
uv run ruff format --check .
openspec validate define-klaro-mvp --strict
```

## Questionnaires

| Capability | Scenario | Executable test(s) |
| --- | --- | --- |
| questionnaires | Create from JSON | `tests/test_creation_api.py::test_json_creation_returns_only_absolute_url_and_expiry` |
| questionnaires | Create from YAML | `tests/test_creation_api.py::test_yaml_creation_has_the_same_questionnaire_structure` |
| questionnaires | Unsupported or malformed input | `tests/test_creation_api.py::test_unsupported_media_types_are_415_without_pushover`<br>`tests/test_creation_api.py::test_malformed_bodies_are_400_without_pushover` |
| questionnaires | Valid question types | `tests/test_models.py::test_valid_questions_receive_sequential_ids_and_preserve_options` |
| questionnaires | Unsupported fields or values | `tests/test_models.py::test_unknown_question_fields`<br>`tests/test_models.py::test_unsupported_question_types` |
| questionnaires | Oversized request body | `tests/test_creation_api.py::test_oversized_body_is_413_without_parsing_or_pushover` |
| questionnaires | Malformed recipient key | `tests/test_creation_api.py::test_missing_or_invalid_recipient_is_400_without_pushover` |
| questionnaires | Pushover queues the notification | `tests/test_creation.py::test_acceptance_publishes_previously_invisible_pending_record` |
| questionnaires | Recipient opens a racing link | `tests/test_creation.py::test_acceptance_publishes_previously_invisible_pending_record` |
| questionnaires | Pushover rejects the recipient | `tests/test_creation.py::test_rejection_and_upstream_failure_delete_pending_and_map_errors` |
| questionnaires | Pushover outcome is unknown | `tests/test_creation.py::test_ambiguous_transport_failure_deletes_pending` |
| questionnaires | URL is the only credential | `tests/test_abuse_routes.py::test_omitted_allowlist_permits_unauthenticated_creation`<br>`tests/test_retrieval_api.py::test_full_json_before_answering_has_stable_ids_and_null_answers` |
| questionnaires | Unknown or deleted URL | `tests/test_retrieval_api.py::test_unknown_expired_and_confirmed_tokens_have_identical_404` |
| questionnaires | Multiple-question notification | `tests/test_pushover.py::test_notification_content_and_acceptance` |
| questionnaires | Pushover length limits | `tests/test_pushover.py::test_display_text_is_truncated_but_complete_url_is_preserved` |
| questionnaires | Render on a narrow screen | `tests/test_browser_forms.py::test_narrow_viewport_and_keyboard_submission` |
| questionnaires | Assets are self-contained | `tests/test_assets.py::test_browser_loads_only_same_origin_assets` |
| questionnaires | Incomplete or forged answers | `tests/test_submission_api.py::test_invalid_submissions_return_422_and_preserve_active_state` |
| questionnaires | Valid submission | `tests/test_submission_api.py::test_valid_htmx_submission_persists_arrays_and_returns_read_only_fragment` |
| questionnaires | Concurrent submissions | `tests/test_submission_api.py::test_concurrent_submissions_have_exactly_one_winner` |
| questionnaires | Questionnaire already answered | `tests/test_submission_api.py::test_duplicate_submission_is_409_and_preserves_original_answers` |
| questionnaires | Poll before answering | `tests/test_retrieval_api.py::test_full_json_before_answering_has_stable_ids_and_null_answers` |
| questionnaires | Read after answering | `tests/test_retrieval_api.py::test_full_json_after_answering_is_complete_and_non_destructive` |
| questionnaires | Answer is not ready | `tests/test_retrieval_api.py::test_answer_only_before_and_after_submission_is_repeatable` |
| questionnaires | Answer is ready | `tests/test_retrieval_api.py::test_answer_only_before_and_after_submission_is_repeatable` |
| questionnaires | Connect while awaiting an answer | `tests/test_sse.py::test_active_stream_has_immediate_status_and_transport_headers` |
| questionnaires | Stream transport protections | `tests/test_sse.py::test_active_stream_has_immediate_status_and_transport_headers` |
| questionnaires | Answer arrives while connected | `tests/test_sse.py::test_answer_arrives_on_open_stream_and_closes_without_polling` |
| questionnaires | Answer predates the connection | `tests/test_sse.py::test_already_answered_stream_immediately_sends_answer_and_closes` |
| questionnaires | Questionnaire expires while connected | `tests/test_sse.py::test_expiry_is_terminal_and_later_connection_is_404` |
| questionnaires | Heartbeat proves liveness | `tests/test_sse.py::test_observable_heartbeat_arrives_on_schedule_and_stream_remains_open` |
| questionnaires | Interrupted stream reconnects | `tests/test_sse.py::test_interrupted_stream_reconnects_to_current_answer_without_replay` |
| questionnaires | Heartbeats do not extend retention | `tests/test_sse.py::test_heartbeats_do_not_extend_retention` |
| questionnaires | Confirm an answer | `tests/test_confirmation_api.py::test_successful_confirmation_deletes_and_repetition_is_generic_404` |
| questionnaires | Confirm too early or twice | `tests/test_confirmation_api.py::test_confirmation_before_answer_is_409_and_preserves_active_record`<br>`tests/test_confirmation_api.py::test_successful_confirmation_deletes_and_repetition_is_generic_404` |
| questionnaires | Expire before or after answering | `tests/test_expiry.py::test_lazy_active_expiry_does_not_extend_on_reads`<br>`tests/test_expiry.py::test_lazy_answered_expiry` |
| questionnaires | Cleanup without polling | `tests/test_expiry.py::test_cleanup_removes_active_and_answered_without_access`<br>`tests/test_expiry.py::test_scheduler_cleans_without_access_and_starts_once` |
| questionnaires | Restart after answering | `tests/test_expiry.py::test_restart_recovers_state_and_removes_stale_pending` |
| questionnaires | Invalid startup configuration | `tests/test_config.py::test_mandatory_fields`<br>`tests/test_config.py::test_unknown_fields_are_errors` |
| questionnaires | Upstream failure is logged | `tests/test_security.py::test_upstream_diagnostic_log_is_actionable_without_secrets` |

## Abuse protection

| Capability | Scenario | Executable test(s) |
| --- | --- | --- |
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
| abuse-protection | Other failures do not increase backoff | `tests/test_abuse_integration.py::test_excluded_pushover_response_failures_do_not_trigger_backoff`<br>`tests/test_abuse_integration.py::test_network_failures_do_not_trigger_backoff` |
| abuse-protection | Wait elapses and delivery succeeds | `tests/test_abuse_integration.py::test_acceptance_resets_next_recipient_rejection_to_one_minute` |
| abuse-protection | Rate limit and backoff coincide | `tests/test_abuse.py::test_longer_backoff_delay_wins_when_rate_limit_also_applies`<br>`tests/test_abuse.py::test_longer_rate_delay_wins_when_backoff_also_applies` |
| abuse-protection | Service restarts | `tests/test_abuse_routes.py::test_restart_resets_fixed_window_state`<br>`tests/test_abuse_routes.py::test_restart_resets_recipient_backoff_state` |
