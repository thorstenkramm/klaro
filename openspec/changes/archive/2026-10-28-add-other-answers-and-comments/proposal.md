# Proposal

## Why

Fixed options cannot express an unlisted answer or context for a selection. Per-question opt-ins will provide these capabilities while preserving complete, single-submission questionnaires.

## What Changes

- Accept strict boolean `allow_other` and `allow_comments`, defaulting to false.
- Add the fixed English Other option and optional per-question comments, each trimmed and limited to 2,000 Unicode code points. Other requires text when selected; comments never replace a selection.
- Persist texts atomically with choices and `answered_at`; populate existing `other`/`comment` response fields. Full definitions additionally expose both flags; answer-only/SSE do not include flags.
- Add accessible mobile-first text controls, native details/summary comments, validation re-population and read-only text displays.
- Set a separate 524,288-byte answer POST cap while creation stays at 65,536 bytes; HTMX `413` handling preserves the current form. The byte cap remains an independent aggregate limit, including URL-encoding overhead.
- **BREAKING (storage):** introduce schema 3 for richer submissions, deployed to a fresh data directory without migration or automatic deletion.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `questionnaires`: opt-in schema fields, complete submissions, response definitions, persistence, mobile text entry and answer request limits.

## Impact

Touches models, answer validation, persistence/projections, Flask request limits, Jinja templates, local CSS/JS, API/browser/concurrency/restart tests and documentation. No new services or runtime dependencies. Builds on `unify-response-format` and follows `create-and-wait-stream`; apply and synchronize in that order. Recommendation metadata remains empty until the next change.
