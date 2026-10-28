# Tasks

## 1. Error contract and configuration

- [x] 1.1 Map parser `RecursionError` to `400 invalid_request` and add the JSON `500` handler with explicit-HTML fallback; verify JSON and YAML nesting, no Pushover call, and three `Accept` variants without exception text.
- [x] 1.2 Reject `public_address` paths at startup, keep trailing-slash normalization, and document root-only hosting; verify rejected and accepted addresses.

## 2. Abuse controls and stored records

- [x] 2.1 Key rate limits and backoff by IPv4 address or IPv6 /64 (IPv4-mapped as IPv4) and expire idle backoff state; verify unit, route, README, and rotation tests.
- [x] 2.2 Treat unreadable records as unknown on every route, log once without token, and delete after the lifetime since last modification; verify five corruption kinds, logging, cleanup, and restart recovery.

## 3. Answer submission feedback

- [x] 3.1 Add the persistent live region, swap focus handling, `hx-sync`/`hx-disabled-elt`, hardened htmx configuration, valid radio-group ARIA, alert-wrapped error lists, and accessible submit contrast; verify focus, announcements, duplicate dropping, and axe WCAG 2.x A/AA checks in Chrome.
- [x] 3.2 Present the HTML request-too-large page only for plain answer forms and document answer submission as browser-only; verify creation, confirmation, HTMX, and plain-form 413 responses.

## 4. Integrated verification

- [x] 4.1 Add the scenarios to the implemented-delta coverage list and run full pytest with coverage floor, Ruff lint/format, strict mypy, jscpd threshold, and strict OpenSpec validation.

## Workflow follow-up

- Apply after render-basic-markdown; synchronize and archive after all predecessors.
