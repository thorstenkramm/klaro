# Spec Delta

## Purpose

Limits notification abuse without introducing accounts by filtering questioner labels, constraining creation attempts per client IP, and backing off clients that repeatedly submit recipient keys rejected by Pushover.

## ADDED Requirements

### Requirement: Unauthenticated questioner model

Questioner operations SHALL NOT require an API token or user account. `X-Questioner` SHALL be treated only as a caller-supplied display and filtering label, never as authenticated identity.

#### Scenario: No allowlist configured

- **WHEN** `klaro.questioners` is omitted and an otherwise valid creation request supplies any non-empty questioner label
- **THEN** the questioner filter permits the request without requiring any other credential

### Requirement: Exact questioner allowlist

When `klaro.questioners` is configured, the service SHALL compare the complete `X-Questioner` value exactly and case-sensitively. An explicitly empty list SHALL deny every questioner; an omitted list SHALL permit every syntactically valid label.

#### Scenario: Label is not allowed

- **WHEN** the supplied label differs from every configured entry by case, whitespace, or content
- **THEN** the service returns `403 Forbidden`, does not call Pushover, and does not retain a questionnaire

#### Scenario: Empty allowlist

- **WHEN** `klaro.questioners = []` is configured
- **THEN** every creation request is rejected with `403` until the configuration changes

### Requirement: Questioner-label validation

`X-Questioner` SHALL contain 1-100 characters and at least one non-whitespace character. Invalid labels SHALL fail before allowlist evaluation or Pushover delivery.

#### Scenario: Missing or blank label

- **WHEN** the questioner header is missing, empty, whitespace-only, or longer than 100 characters
- **THEN** the service returns `400` with a field-specific error and does not call Pushover

### Requirement: Client IP determination

The service SHALL use the direct peer IP by default. It SHALL honor forwarded client-address information only when the immediate peer is configured in `klaro.trusted_proxies`; forwarding headers from every other peer SHALL be ignored.

#### Scenario: Untrusted forwarding header

- **WHEN** a direct client supplies `X-Forwarded-For` but its peer is not a trusted proxy
- **THEN** rate limiting and backoff use the direct peer IP rather than the spoofed header value

#### Scenario: Trusted reverse proxy

- **WHEN** a request arrives through a configured trusted proxy with a sanitized client-address header
- **THEN** rate limiting and backoff use the forwarded end-client IP consistently

### Requirement: Fixed-window creation rate limit

The service SHALL allow at most five `POST /` creation attempts per remote IP in a 60-second fixed window started by the first attempt. Every attempt SHALL count, including validation, allowlist, upstream, rate-limit, and backoff rejections; rejected attempts SHALL NOT extend the window.

#### Scenario: Sixth attempt in one window

- **WHEN** an IP has already made five creation attempts within the current window and makes another before it ends
- **THEN** the sixth attempt returns `429`, does not call Pushover, and leaves the original window-ending time unchanged

#### Scenario: Invalid attempts consume quota

- **WHEN** an IP makes five creation attempts that fail schema validation or questioner filtering
- **THEN** those attempts still exhaust the five-attempt allowance for that window

#### Scenario: New window begins

- **WHEN** the 60-second window expires
- **THEN** the next creation attempt starts a new window with an allowance of five

### Requirement: Rate-limit feedback and scope

Rate-limited creation attempts SHALL return JSON error code `rate_limited` and a `Retry-After` header containing whole seconds until the window resets. Answering, static assets, retrieval, and confirmation SHALL NOT consume or be blocked by this creation quota.

#### Scenario: Client can schedule a retry

- **WHEN** a creation attempt exceeds the fixed-window allowance with 17 seconds remaining
- **THEN** the service returns `429` and `Retry-After: 17` without creating a questionnaire

#### Scenario: Answer traffic is independent

- **WHEN** an IP has exhausted its creation quota
- **THEN** it can still load an answer page, submit an answer, retrieve JSON, and confirm an answer subject only to the lifecycle rules

### Requirement: Recipient-rejection backoff schedule

Only a Pushover response that specifically rejects the recipient key SHALL increment that remote IP's recipient backoff. Delays SHALL be 1, 2, 4, 8 minutes and continue doubling after each allowed request that Pushover rejects for the recipient, capped at 60 minutes.

#### Scenario: First recipient rejection

- **WHEN** Pushover rejects an otherwise valid request because its recipient key is invalid
- **THEN** that request returns `422` and subsequent creation attempts from the same IP enter a 60-second backoff

#### Scenario: Repeated recipient rejections

- **WHEN** each backoff has elapsed and the next allowed request is again rejected specifically for its recipient
- **THEN** the next delay doubles the previous delay until it reaches, and remains capped at, 3600 seconds

#### Scenario: Other failures do not increase backoff

- **WHEN** a request fails local key validation, questioner filtering, Pushover quota, application authentication, network connectivity, or an upstream server error
- **THEN** the recipient-backoff level is not increased

### Requirement: Backoff enforcement and reset

During recipient backoff, creation attempts SHALL return `429` with JSON error code `recipient_backoff` and `Retry-After`, without calling Pushover or changing the delay. A successful Pushover acceptance SHALL reset the IP's backoff level.

#### Scenario: Wait elapses and delivery succeeds

- **WHEN** an IP makes a creation attempt after its backoff expires and Pushover accepts the notification
- **THEN** the request proceeds normally and the IP's next recipient rejection starts again at a 60-second delay

#### Scenario: Rate limit and backoff coincide

- **WHEN** both controls reject the same creation attempt with different remaining delays
- **THEN** the service returns one `429` without calling Pushover and sets `Retry-After` to the longer remaining delay

### Requirement: In-memory control state

Rate-limit windows and recipient-backoff state SHALL be held in memory and MAY be lost on restart. The supported deployment SHALL be one Klaro instance with one Gunicorn worker so these counters are authoritative rather than per-worker.

#### Scenario: Service restarts

- **WHEN** Klaro restarts with active rate-limit or backoff state
- **THEN** those temporary controls start empty while persisted questionnaires and their original expiry times remain intact
