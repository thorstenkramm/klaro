# Design

## Context

See proposal.md. Current `Question` contains ID/name/type/options only; `validate_answers` returns ID-to-option tuples. Schema 2 stores those tuples and answered_at atomically. Public text fields are hard-coded null. `app.py` has one global 64 KiB limit and a fixed JSON 413 handler; `klaro.js` only updates progress. The form is still one label per option. Templates are autoescaped, and HTMX's inline indicator style injection has been disabled for CSP compatibility.

## Goals / Non-Goals

**Goals:** Add opt-in text without weakening completeness, atomicity, request bounds, or the no-JavaScript path; retain one shared public answer projection.

**Non-Goals:** Standalone free-text question types, per-option comments, Markdown for respondent text, recommendations or migration of existing records.

## Decisions

1. Add strict bool defaults to `Question`, persist them in definitions and expose both in full JSON. Do not accept numeric/string truthiness. Keep polling/SSE shapes stable. Only enable the corresponding form-field names when the flag is true; reject disabled fields even if empty and reject repeated text parameters to prevent ambiguous decoding.
2. Introduce a typed submitted-answer value carrying `answered: tuple[str, ...]`, `other: str | None`, and `comment: str | None`, mapped by internal qid. This replaces separate independently updated text dictionaries, so validation and storage cannot disagree about the winning submission. Preserve an offered-choice projection for existing read-only consumers as useful; adapt callers and storage-level fixtures deliberately.
3. Treat reserved choice `other` separately from index lookup. Check radio/checkbox cardinality on all selected choices first. Resolve indices to exact source strings in submitted order. Trim Other only when selected and require nonempty text; unselected Other text is ignored after checking duplicate field cardinality. Trim optional comments to null when blank. Validate normalized values at 2,000 Unicode code points, then store the complete result and answered_at under the existing per-token lock before subscriber notification.
4. Introduce storage schema 3, with per-question structured answers and the new definition flags. Decoder checks require a matching answer for every qid, permitted text only, valid cardinality including Other-only choices, and timestamp/state consistency. Reject unsupported versions; recovery must not migrate or delete them automatically. Fresh-directory deployment follows the user's no-production-data decision.
5. Retain 65,536 as the default request limit; set a per-request 524,288 limit only for the answer POST route before any body/form reads, excluding confirmed=1. Ensure form-parser limits do not silently impose a lower cap (including multipart form-memory overhead); cap raw bytes irrespective of Content-Length, and keep confirmation bounded. Werkzeug's per-request limit facilities are available through Flask 3.1; verify their exact behavior during implementation using current docs and boundary tests. Do not merely raise the global limit, because creation abuse limits must remain unchanged.
6. Return an accurate size-specific 413. HTMX leaves its current DOM intact; a static accessible error region and a same-origin `htmx:responseError` listener show the message, focus it and preserve selections/text. Do not add 413 to the swap-true rules or render a new empty form. Full-page 413 has understandable text; do not parse or echo an oversized request. Native back navigation is the recovery path, without promising browser cache retention.
7. Refactor `.kl-option` into a container with `.kl-option__head` label, following `tmp/handover-feedback-01/ui-design.md`. Other's textarea is a sibling outside that label, visible on selection using progressive CSS `:has`; fallback is always visible. Comments use native details/summary with a 44px icon target and accessible name. Render nonempty/error comments open after 422. Escape and repopulate all raw submitted text on validation errors, while only normalized valid text reaches storage. Render read-only Other and Your comment separately with preserved line breaks.
8. Use server-side code-point validation plus an optional `Array.from(value).length` counter. Do not use HTML maxlength=2000, which counts UTF-16 units and rejects valid 2,000-character emoji text. The static hint and server validation also work without scripts. Progress must not count comments as an answer; if counting Other, require nonblank Other text. Listen to both input and change after HTMX swaps.

## Risks / Trade-offs

- A 512 KiB cap is not enough for every combination of valid Unicode fields → document it as an independent aggregate cap and test a 20-question worst-case URL-encoded submission. Forty 2,000-code-point fields of four-byte characters alone encode to 960,000 bytes, before field overhead. Preserve the agreed cap rather than claiming all valid field combinations fit.
- Client/server character counting differs → code-point counter and server boundary tests, including supplementary Unicode and newlines.
- Template refactor affects labels, errors and selection styling → browser tests at 320px, keyboard and JavaScript-disabled cases, plus actual Chrome CSP checks.
- Partial storage transition or race → concurrent submissions with distinct choices/text/timestamps, restart and SSE equality tests.

## Migration Plan

Apply after create-and-wait and unified responses. Stop the single worker, select a new empty owned data directory, deploy schema 3. Do not auto-delete earlier directories. Rollback uses the previous build with its own compatible empty directory. Update API examples and storage-version docs; preserve original expiry and answer timestamp on normal same-version restart. Synchronize/ archive changes in dependency order through the separate archive workflow.
