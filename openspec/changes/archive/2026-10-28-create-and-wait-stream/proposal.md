# Proposal

## Why

Clients currently need to parse the creation response and make a separate invocation to wait for answers. A same-origin redirect enables creation and streaming with one `curl -L` invocation.

## What Changes

- Opt in through an explicitly preferred `Accept: text/event-stream` on creation; return an empty `303` with relative `Location: /<token>` only after successful publication.
- Keep ordinary creation at `201` JSON and creation errors as JSON with their existing statuses.
- Document and execute a single-curl journey, including URL recovery when an answer arrives before the redirected GET and no waiting status is emitted.
- Use the unified SSE contract from `unify-response-format`; retain explicit confirmation, expiry and single submission.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `questionnaires`: creation negotiation, redirect and single-invocation stream consumption.

## Impact

Touches `src/klaro/app.py`, creation/SSE integration tests, README examples and current scenario coverage. No new runtime dependencies or storage change. Apply after `unify-response-format`; synchronize specifications in that order. This is the next change in the feedback sequence.
