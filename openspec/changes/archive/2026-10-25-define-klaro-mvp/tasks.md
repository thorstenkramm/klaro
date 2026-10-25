# Tasks

## 1. Project foundation and configuration

- [x] 1.1 Create the Python 3.11+ package, `pyproject.toml`, test tooling, Flask/Jinja, PyYAML, requests, Gunicorn, and gevent dependencies, and committed `uv.lock`; verify `uv sync`, an application-package import, and `uv run pytest` succeed.
- [x] 1.2 Implement typed TOML loading and startup validation for every field in `design.md`, including defaults, storage checks, priority range, proxy ranges, positive SSE heartbeat intervals, and public-URL length; verify valid, omitted, malformed, and unsafe configurations with unit tests.
- [x] 1.3 Add the configuration reference and a complete example to `README.md`; verify the example is parsed by the configuration tests and all documented defaults match the implementation.

## 2. Creation input and validation

- [x] 2.1 Implement the 65,536-byte body limit, explicit JSON/YAML media-type handling, strict UTF-8 decoding, safe YAML loading, and duplicate-key rejection; verify JSON/YAML parity and malformed, unsafe, oversized, and unsupported inputs in parser tests.
- [x] 2.2 Implement questionnaire schema validation, sequential question IDs, exact option preservation, and the documented question, option, string, and unknown-field limits; verify every boundary and reject `confirm_reception`, free text, duplicate options, and invalid shapes in unit tests.
- [x] 2.3 Implement recipient-key and questioner-label syntax validation; verify all 30-character key boundaries and blank, over-length, and valid questioner labels in unit tests, with no outbound call on failure.

## 3. Persistent lifecycle

- [x] 3.1 Implement 256-bit token generation, versioned questionnaire records, protected storage directories, atomic writes and deletion, and non-secret persistence; verify round trips, file permissions, atomic replacement, token entropy source, and absence of recipient keys in stored files with tests.
- [x] 3.2 Implement per-token locking and pending, active, answered, confirmed, and not-found transitions; verify early confirmation, repeated submission, generic deletion behavior, and concurrent first-submission-wins tests without partial records.
- [x] 3.3 Implement injected clocks, lazy expiry, 30-second scheduled cleanup, and restart recovery including stale-pending removal; verify active and answered expiry, unchanged deadlines, cleanup without access, and restart behavior with fake-clock and filesystem tests.
- [x] 3.4 Implement worker-local per-token subscriber notification after answer and expiry transitions, with locked registration followed by a state recheck; verify that concurrent submissions, expiry, and new or interrupted subscribers cannot miss the current terminal state.

## 4. Pushover integration and publication

- [x] 4.1 Implement plain-text notification construction, complete supplementary URLs, display-text truncation, configured sound and priority, TLS verification, timeouts, and the two-call concurrency bound; verify content and length limits with mocked-transport tests.
- [x] 4.2 Implement Pushover response classification and the no-automatic-retry policy; verify accepted-and-queued, structured recipient rejection, quota and token errors, malformed responses, server errors, timeouts, and connection failures in unit tests.
- [x] 4.3 Implement creation coordination so pending state publishes only after acceptance and is deleted after every failure; verify publication order, pending-URL invisibility, cleanup, `422`/`502` mapping, and no secret logging in integration tests.

## 5. Abuse protection

- [x] 5.1 Implement direct-peer and trusted-proxy client-IP resolution with IP/CIDR configuration; verify spoofed-header rejection and trusted IPv4/IPv6 proxy cases in unit tests and document proxy sanitization in `README.md`.
- [x] 5.2 Implement the per-IP five-attempt, 60-second fixed window with every creation attempt counted and rejected attempts not extending the window; verify sixth-request rejection, reset timing, invalid-attempt accounting, and exact `Retry-After` values with a fake clock.
- [x] 5.3 Implement recipient-only exponential backoff, its 60-minute cap, success reset, blocked-request behavior, and longer-delay selection when both controls apply; verify the complete schedule and all excluded failure classes in unit and integration tests.
- [x] 5.4 Connect questioner allowlist, rate limiting, and backoff to the creation pipeline without affecting non-creation routes; verify omitted, exact, case-mismatched, and empty allowlists, all counted rejection paths, and independent answering traffic in route tests.
- [x] 5.5 Document the unauthenticated trust model, exact allowlist semantics, fixed-window algorithm, backoff schedule, restart reset, and one-worker limitation in `README.md`; verify the documented examples and values against the abuse-control tests.

## 6. Public HTTP API

- [x] 6.1 Implement `POST /` with consistent creation JSON and sanitized error envelopes; verify `201`, `400`, `403`, `413`, `415`, `422`, `429`, and `502` responses and ensure no Pushover call occurs for local failures.
- [x] 6.2 Implement full JSON retrieval, `answer_only=1`, browser negotiation through `Accept`, and generic `404` responses; verify pending and answered bodies, repeated non-destructive reads, stable question IDs, and no token or recipient-key leakage.
- [x] 6.3 Implement POST-only reception confirmation; verify successful deletion, `409` before answering, repeated-confirmation `404`, and that GET with `confirmed=1` never mutates state.
- [x] 6.4 Implement SSE negotiation on the existing secret URL with immediate status, observable heartbeat, terminal answer and expiry events, stream closure, reconnection state, and anti-buffering headers; verify framing, timing, already-answered connections, disconnected reconnects, and no polling with streamed-response tests.
- [x] 6.5 Replace the README's illustrative creation and retrieval examples with final JSON and YAML requests, `Accept` negotiation, response schemas, POST confirmation, and an SSE client example; verify each example against the running application with Pushover mocked.

## 7. Mobile answering interface

- [x] 7.1 Vendor pinned UIkit and HTMX files with their license notices and same-origin static routes; verify production package inclusion, successful asset responses, and a browser test that records no CDN or third-party request.
- [x] 7.2 Build mobile-first Jinja templates with semantic fieldsets, explicit labels, required radio/checkbox controls, visible errors, HTMX submission, and normal-form fallback; verify narrow-viewport, keyboard, and no-JavaScript behavior in browser tests.
- [x] 7.3 Implement answer submission and HTMX result fragments using the locked lifecycle transitions; verify incomplete and forged answers preserve active state, valid answers persist arrays, duplicate submissions return `409`, and later browser views are read-only.
- [x] 7.4 Add no-store, no-referrer, nosniff, and content-security headers plus token-path log redaction across questionnaire routes; verify headers and sanitized logs in integration tests and document the shared-URL risk and one-submission rule in `README.md`.

## 8. Production packaging and operations

- [x] 8.1 Add the production Gunicorn entry point using the same TOML selection as the application, exactly one gevent worker with bounded connections, and one worker-owned cleanup scheduler; verify the startup command, listen address, scheduler count, and ordinary request completion while long-lived SSE streams remain open in a subprocess smoke test.
- [x] 8.2 Build source and wheel distributions containing templates, static assets, license notices, and locked dependencies; verify installation into a clean temporary environment and a startup smoke test without relying on the source tree.
- [x] 8.3 Complete operational documentation for `uv`, data-directory ownership and permissions, reverse proxies, SSE buffering and heartbeat configuration, reconnection after restart, clock synchronization, timeout/dead-link behavior, expiry, backups, rollback, and the prohibition on multiple workers or instances; verify every command and path in a clean test environment.

## 9. End-to-end verification

- [x] 9.1 Run the complete unit, integration, SSE, concurrency, and browser suites plus linting and `openspec validate define-klaro-mvp --strict`; verify all checks pass and every specification scenario has an executable test or an explicitly recorded manual browser check.
- [x] 9.2 Run a JSON journey using SSE and a YAML journey using polling through creation, mocked Pushover acceptance, answering, answer delivery, confirmation, and generic `404`; verify full answers arrive without an SSE polling request, two polling reads remain non-destructive, and persisted files and HTTP responses are exact.
- [x] 9.3 Run combined restart, SSE reconnect and heartbeat, expiry, rate-limit, recipient-backoff, open-stream concurrency, and concurrent-submission scenarios with security logs enabled; verify current state survives restart, heartbeats arrive on schedule, ordinary routes progress, temporary controls reset, one answer wins, and no credential or secret URL appears in logs.

## Workflow follow-up

- Archive the change only after implementation, review, and all end-to-end verification are complete.
- Verify that archiving produces the two main capability specifications without placeholder purposes or dropped scenarios.
