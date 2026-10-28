# Tasks

## 1. Creation validation and persisted timestamps

- [x] 1.1 Enforce exact case-sensitive question-name uniqueness in `models.py`; update creation documentation and model/API tests to verify the later zero-based field path, exact error message, `400 invalid_request`, no notification or retained file, and acceptance of case/whitespace differences.
- [x] 1.2 Add nullable `answered_at`, schema version 2, and state/timestamp decoding invariants in `storage.py`; record the timestamp inside the existing locked atomic answer transition. Verify storage round trips, pending/awaiting null values, invalid-state rejection, timestamp preservation after reads/restart, and one winning answer/timestamp under concurrent submission.
- [x] 1.3 Document the empty-data-directory deployment and rollback procedure without migration or automatic deletion; verify operations documentation and storage/recovery tests against fresh temporary directories.

## 2. Index-based answering forms

- [x] 2.1 Change answer validation to canonical ASCII 1-based index strings mapped back to exact source option text. Update unit tests for cardinality, unknown fields, repeated indices, range bounds, noncanonical encodings, submitted order, and numeric-looking option strings; verify `tests/test_answers.py` passes.
- [x] 2.2 Update form values and validation re-selection to indices while preserving labels, internal field IDs, full-page/HTMX error rendering, and read-only answers. Update HTML form documentation and template/submission/browser tests; verify keyboard, mobile, no-JavaScript, and `422` selection-preservation behavior.
- [x] 2.3 Update HTTP submission fixtures throughout integration, abuse-route, security, restart, and end-to-end tests to send indices while keeping storage-level fixtures as source text where appropriate; verify those affected suites preserve lifecycle and abuse-control assertions.

## 3. Unified public responses

- [x] 3.1 Introduce shared question and answer-only projections separate from storage serialization, and wire full JSON and polling routes to them. Verify exact key sets, creation order, original source strings, null/empty extension defaults, timestamp stability, repeated non-destructive polling, and absence of IDs, legacy status, and secrets in retrieval tests.
- [x] 3.2 Update README full/answer-only examples and their executable tests, including output-only extension fields and continued rejection of extension input keys; verify documentation examples against real application responses and confirm creation still returns `201` and confirmation still returns `{"status":"confirmed"}`.

## 4. SSE integration

- [x] 4.1 Supply the configured absolute URL to SSE and emit the new `status` projection. Verify initial and reconnected waiting streams contain the creation URL and original expiry, ignore hostile Host values when building that URL, and retain retry framing, heartbeat timing, and cache/buffering protections.
- [x] 4.2 Reuse the answer-only serializer for terminal answers and emit expiry from the subscription's retained deadline. Verify semantic equality of SSE and polling data, immediate already-answered delivery, no extra poll for open-stream answers, expiry after cleanup deletion, terminal closure, and subscriber release.
- [x] 4.3 Update SSE README examples and security tests to describe the URL exception and new payloads; verify executable examples, unchanged confirmation, and redaction of tokens/credentials from both application and Gunicorn logs.

## 5. Coverage and integrated verification

- [x] 5.1 Replace the archived-MVP-only coverage lookup and fixed count with current scenario-to-test metadata covering main specs plus this delta. Verify every effective scenario has an existing executable test reference and that coverage remains valid after simulated delta synchronization, without changing archived artifacts or the real main specs during implementation.
- [x] 5.2 Run complete JSON/SSE and YAML/polling journeys using index submissions and exact schema-2 persisted data; verify matching answer timestamps across polling/SSE/restart, non-destructive reads, explicit confirmation deletion, generic `404`, and no credential logging.
- [x] 5.3 Run `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, and `openspec validate unify-response-format --strict`; verify the production launcher/open-stream concurrency and clean wheel installation tests pass with the new contract and resolve all failures before completion.

## Workflow follow-up

- Review the completed implementation before synchronizing and archiving this change through the archive workflow.
- Verify current scenario coverage after synchronization and archive; retain historical artifacts unchanged.
- Continue the remaining feedback changes separately: create-and-wait, other/comments with its answer-body limit, dedicated-key recommendations, and Markdown.
