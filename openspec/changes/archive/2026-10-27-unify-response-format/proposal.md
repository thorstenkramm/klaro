# Proposal

## Why

Questionnaire retrieval, answer-only polling, and SSE currently expose three different response shapes and require clients to map generated question IDs back to question definitions. Unifying these representations around question names and an explicit answer timestamp will make the API easier to consume and provide a stable foundation for comments, custom answers, recommendations, and Markdown content.

## What Changes

- **BREAKING:** Replace questionnaire `status` in retrieval and SSE payloads with `answered_at`, an RFC 3339 UTC timestamp recorded when the valid submission is stored. Before answering, `answered_at` is `null`; expired and confirmed questionnaires continue to return generic `404` responses.
- **BREAKING:** Remove question IDs from public JSON. Full retrieval returns `expires_at`, `answered_at`, and an ordered `questions` array containing each question's `name`, `type`, offered `answers`, and selected `answered` values. `answered` is `null` before submission and an array of source option strings afterward. `created_at` and `questioner` remain internal and are not added to the response.
- Establish stable per-question response fields for subsequent changes: `other` and `comment` default to `null`, while `recommendations` defaults to `[]`. Their corresponding input features are not implemented by this change.
- Make `answer_only=1` a definition-free view of the same model: top-level `answered_at` plus ordered questions containing `name`, `answered`, `other`, `comment`, and `recommendations`, without `type` or offered `answers`. Polling remains non-destructive.
- Emit the SSE `answer` event with exactly the answer-only payload. Emit `status` with `answered_at: null`, the original `expires_at`, and the absolute secret `url`; emit `expired` with `expires_at`. Heartbeats remain unchanged, and confirmation continues to return `{"status":"confirmed"}` because it acknowledges an action rather than describing questionnaire state.
- Require question names to be unique using exact, case-sensitive string comparison. Reject duplicates at creation with `400 invalid_request`, a field error such as `questions.1.name`, and no Pushover call or retained questionnaire.
- Change HTML form option values from option text to 1-based indices. Validate indices against each question and map accepted indices back to source strings for storage and public output, while preserving the existing one-submission lifecycle.
- Persist `answered_at` and move to a new questionnaire storage schema. No migration or compatibility layer is required because the application has no production data or existing API clients; deployment starts with an empty data directory.
- Update API documentation and all affected model, storage, retrieval, submission, template, SSE, restart, concurrency, and end-to-end tests. Create-and-wait redirects, free-text features, recommendation input, Markdown rendering, and answer-body limit changes remain separate changes.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `questionnaires`: Change the schema and limits, full and answer-only retrieval contracts, SSE status/answer/expiry payloads, answer submission encoding, and persisted answer metadata. Preserve capability URLs, atomic first-submission behavior, expiry, confirmation semantics, and notification publication rules.

## Impact

- Public JSON and SSE contracts change without backward compatibility; the confirmation response and HTML answering lifecycle remain intact.
- Affected implementation areas include `src/klaro/models.py`, `answers.py`, `storage.py`, `app.py`, `sse.py`, and the answering form templates. Documentation and examples in `README.md` change accordingly.
- Storage records gain answer timestamps and a new schema version. No data migration or new runtime dependency is needed.
- The verification matrix and retrieval, submission, template, SSE, persistence, browser, and end-to-end tests must assert the new shapes and index-to-text mapping, including exact duplicate-name errors and identical answer-only/SSE answer payloads.
- Follow-up changes can add create-and-wait streaming, comments and custom answers, recommendation values, and Markdown without reintroducing public question IDs or separate answer representations.
