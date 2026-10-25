# Proposal

## Why

Klaro will give API clients a lightweight back channel from Pushover notifications to structured answers, without requiring recipients to install another application or sign in. The repository currently contains usage notes and unsorted constraints but no implementation or unambiguous product contract; this change defines an MVP that a developer can implement and test without guessing its central lifecycle or trust decisions.

## What Changes

- Introduce a self-hosted HTTP service that accepts questionnaires in JSON or YAML, sends a Pushover notification, and publishes the questionnaire only after Pushover accepts and queues that notification.
- Support questionnaires containing required single-choice radio and multiple-choice checkbox questions. A questionnaire accepts exactly one complete submission, even when a Pushover group receives its link.
- Provide a mobile-first answering page using UIkit and HTMX assets served by Klaro itself; no CDN, recipient account, or separate application is required.
- Let questioners wait for answers through server-sent events (SSE) on the same secret URL, with immediate state, observable heartbeats every 15 seconds by default, reconnection guidance, and terminal answer or expiry events.
- Use one high-entropy secret URL for answering, answer retrieval, confirmation, and SSE streaming. Possession of the URL is the only access check for those operations.
- Allow non-destructive answer retrieval until the questioner explicitly confirms reception, which permanently deletes the questionnaire and answer.
- Delete questionnaires automatically after a configurable lifetime measured from creation, defaulting to 24 hours, whether or not they have been answered.
- Accept unauthenticated questioner requests, with an optional exact, case-sensitive `X-Questioner` allowlist, per-IP creation rate limiting, and per-IP exponential backoff for recipient-specific Pushover rejections.
- Persist questionnaire data beneath a configured data directory and support one Klaro instance with one gevent Gunicorn worker. Serve locally with Python and `uv`; horizontal scaling is outside the MVP.
- Exclude free-text questions, multiple submissions, per-question optional answers, questioner accounts, separate answer/retrieval URLs, actual device-delivery guarantees, emergency-notification receipts, durable SSE event replay, and multi-worker or distributed coordination.

## Capabilities

### New Capabilities

- `questionnaires`: Questionnaire creation and validation, Pushover delivery initiation, mobile answering, single-submission enforcement, answer retrieval and confirmation, SSE answer notification, persistence, and expiry.
- `abuse-protection`: Questioner filtering, per-IP creation rate limits, recipient-specific Pushover rejection backoff, and associated client feedback.

### Modified Capabilities

None.

## Impact

- Adds the initial Python application, automated tests, packaging, and operational documentation to the repository.
- Defines the public creation, answering, retrieval, and confirmation HTTP contracts plus the TOML configuration contract.
- Integrates with the Pushover Message API and requires UIkit, HTMX, a YAML parser, Gunicorn, and gevent dependencies; frontend assets must be distributed locally. One gevent worker supports long-lived SSE streams without per-connection operating-system threads.
- Uses operator-provided Pushover credentials and filesystem storage. It deliberately does not introduce a database, account system, external cache, or shared coordination service.
- Requires revisions to the README examples so they match the finalized JSON/YAML, response-format, confirmation, and expiry behavior.
