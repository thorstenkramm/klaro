# Proposal

## Why

The 2026-10 code review (`tmp/code-review-2026-10-27.md`) found observable behaviour that is unsafe, undocumented, or
inaccessible: deep nesting and unexpected errors broke the JSON error contract, a `public_address` path silently broke
routing, IPv6 clients could bypass creation limits, unreadable records were served as `500` and never deleted, and HTMX
updates lost focus, announced unreliably, and could submit twice. The capability-URL and questioner-label trust model
stays unchanged.

## What Changes

- Reject deeply nested creation bodies with `400 invalid_request`; return the JSON error contract for unexpected `500`
  errors, except to clients that explicitly prefer HTML.
- Reject a `klaro.public_address` that contains a path.
- Group abuse-control clients by IPv4 address or IPv6 /64, count IPv4-mapped addresses as IPv4, and forget recipient
  backoff after one maximum delay of inactivity following the block.
- Treat unreadable stored records like unknown tokens, log them once without their token, and delete them once the
  configured lifetime has passed since their last modification.
- Document answer submission as browser-only; move focus to the error summary or result after HTMX swaps, announce
  results through a persistent live region, and drop duplicate submissions while one is in flight.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `questionnaires`: configuration validation, error contract, unreadable records, and answer-submission feedback.
- `abuse-protection`: client grouping for rate limits and backoff, and backoff-state expiry.

## Impact

Touches `parsing.py`, `routes.py`, `responses.py`, `config.py`, `abuse.py`, `filestore.py`, templates, `klaro.js`,
`klaro.css`, README, and tests. No storage-format change: schema 4 records remain valid. Deployments that configured a
`public_address` with a path no longer start; serve Klaro from the root of its own host name. Clients behind one IPv6 /64
now share a creation allowance.
