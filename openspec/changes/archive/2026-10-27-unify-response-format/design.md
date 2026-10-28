# Design

## Context

See `proposal.md` for motivation and `specs/questionnaires/spec.md` for the public contract. This design is required because the change crosses validation, persistence, HTML forms, HTTP serialization, SSE, and tests.

Current implementation observations:
- `Question.as_dict()` includes internal IDs and is used for storage and public definitions.
- `Questionnaire.answer_dict()` returns the internal ID-to-text mapping; full retrieval, polling, and SSE assemble different public objects around it.
- `FileStore.submit_answers()` holds the per-token lock through atomic replacement and notifies subscribers afterward. There is no answer timestamp today.
- Form values are option text; validation and template re-selection assume text values.
- `Subscription.expires_at` survives deletion, while its expiry snapshot returns no record.
- The verification test compares current main-spec scenarios to the archived MVP matrix and hard-codes 57 scenarios. It needs an approach that accounts for subsequent deltas without rewriting historical artifacts.

## Goals / Non-Goals

**Goals:** Centralize response projection, preserve transactional answer semantics, and change form encoding without changing visible labels or no-JavaScript behavior.

**Non-Goals:** Replacing the internal lifecycle state machine, restructuring all stored question identities, migrating existing data, rendering Markdown, accepting extension inputs, adding redirects, or changing body limits. The later 512 KB answer-limit decision belongs to the other/comments change.

## Decisions

### 1. Keep internal IDs and lifecycle status; introduce public projections

Retain `q1`-style IDs for storage, form names, validation errors, and internal answer mappings. Keep `status` internally for pending/publication/answered transitions. Removing these internals would increase churn without improving the public contract.

Keep storage serialization separate from public serialization. Introduce a shared per-question projection and an answer-only envelope on `Questionnaire`; full retrieval enriches that same projection with `type` and offered `answers`. Polling and SSE `answer` call the identical answer-only serializer. Do not repurpose the internal answer mapping if existing templates still need it.

Iterate the stored question sequence, never answer-map keys, to preserve question order. Preserve selected strings and their submitted order. For this release the extension fields are output constants: `other=null`, `comment=null`, `recommendations=[]`. Do not add input keys or UI controls for them. This avoids prematurely implementing the following changes.

Example after a radio answer:

```json
{
  "expires_at": "2026-10-27T12:00:00Z",
  "answered_at": "2026-10-26T12:01:00Z",
  "questions": [
    {
      "name": "Drink?", "type": "radio", "answers": ["beer", "water"],
      "answered": ["water"], "other": null, "comment": null, "recommendations": []
    }
  ]
}
```

Answer-only removes only the full-response fields `expires_at`, `type`, and offered `answers`. Although recommendations are currently empty metadata, include the field as specified by the existing proposal to keep the shared question projection stable.

### 2. Store the answer timestamp in the winning atomic transition

Add nullable `answered_at` to the record and bump `SCHEMA_VERSION` from 1 to 2. Pending and awaiting-answer records have no answers and a null timestamp; answered records have both. Serialize with existing UTC time helpers and restore it on load. Validate this state/timestamp consistency when decoding version-2 records.

Inside `submit_answers()`, after existence, expiry, and lifecycle checks succeed under the lock, obtain `clock.wall()` and replace status, answers, and timestamp together. Notify only after the atomic write succeeds. Rejecting a duplicate, losing a race, or failing validation never changes the timestamp. Do not derive timestamps during retrieval or from file modification times: either would change the answer's meaning after reads or restart.

Normal restarts retain version-2 records exactly. No reader or migration for version 1 is required; the user confirmed no production data exists.

### 3. Validate exact names and canonical option indices

Maintain a seen-name set during creation and reject the later duplicate at its existing zero-based validation path, before notification or storage. Do not strip or case-fold names.

Form inputs retain internal question IDs as names but send the canonical ASCII decimal representation of the 1-based option index. Compare against a lookup of allowed strings (`"1"` through the option count), rather than permissive integer coercion. This rejects signs, padding, leading zeros, Unicode digits, and fractions predictably. Map valid values to exact source strings; preserve existing cardinality, duplicate-selection, and unknown-field checks.

Canonical syntax is a planning default for the new form wire representation. No legacy-text fallback is provided: a text value that happens to equal a valid index means that index. Test numeric-looking option text explicitly.

On `422`, selected values remain index strings; templates compare against the rendered index while labels still show original text. Preserve the current full-page/HTMX-fragment distinction, accessible error associations, and read-only answered view. No new frontend dependency or redesign is needed.

### 4. Pass the configured URL into SSE; retain the subscription deadline

The retrieval route computes the absolute URL using the same configured URL builder as creation and supplies it to the SSE response/stream. Avoid constructing it from an untrusted Host header. `status` serializes null `answered_at`, the original deadline, and that URL.

Keep the already-answered shortcut: retry hint, terminal answer, close; it does not emit a false awaiting-answer status. The future create-and-wait change must consider its URL-discovery behavior for this fast-answer case separately.

For `expired`, use `Subscription.expires_at` because cleanup may already have removed the record. Do not read storage again to obtain the deadline. Retry framing, named heartbeats, subscription locking and cleanup, current-state reconnects, and buffering/cache headers remain unchanged.

Adding the URL to `status` requires the delta's explicit sensitive-data exception. Answer JSON, terminal answer payloads, error responses, and logs still exclude it. Confirmation stays `{"status":"confirmed"}`; it is an action acknowledgement.

### 5. Verify current contracts without rewriting the archived MVP

Update existing tests to new request/response contracts and preserve meaningful concurrency, expiry, restart, and browser assertions. Add focused coverage for timestamp stability, canonical indices, exact name uniqueness, extension defaults, and equality of SSE/polling projections.

Replace the archived-matrix-only assumption in `tests/test_verification_matrix.py` with current coverage metadata that can account for the main specifications plus this active delta. Map all resulting scenarios to executable tests, retain coverage of unchanged abuse scenarios, and avoid a hard-coded scenario count. When this delta is synchronized/archived, the same current coverage metadata must remain valid against main specs. Historical archived matrices remain historical evidence, not a frozen limit on current coverage.

## Risks / Trade-offs

- Breaking API and form encoding -> update README examples and all consumers/tests together; no compatibility path was requested.
- Timestamp and answer divergence -> one locked atomic write, state invariants, and race/restart tests.
- Wire projections accidentally exposing IDs or secrets -> assert exact key sets and redacted logs, not just the presence of new fields.
- Null extension placeholders could appear to enable input -> document that these fields are output-only until their dedicated changes; keep strict unknown-field rejection.
- Stale test records -> deploy with a new empty data directory. Do not automatically delete or migrate arbitrary files during implementation.

## Migration Plan

There is no production-data migration. Stop the sole instance and configure an empty data directory when deploying the schema-2 build; use fresh temporary directories for tests. Update callers/examples to the new API simultaneously. Rollback uses the previous build with its own empty directory; schema-2 records are not fed to the old reader. Same-version restarts continue to preserve records and timestamps. No live files are deleted as part of this planning or implementation scope.
