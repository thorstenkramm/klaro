# Spec Delta

## Purpose

Provides a complete, short-lived questionnaire lifecycle from an API client's request through Pushover notification, one mobile-friendly response, live answer streams, non-destructive retrieval, explicit acknowledgement, and deletion.

## ADDED Requirements

### Requirement: Questionnaire creation contract

The service SHALL accept `POST /` with `X-Pushover-User` and `X-Questioner` headers and a `questions` array. It SHALL support `application/json` and `application/yaml`, reject unsupported media types, and return the secret URL and expiry after publication.

#### Scenario: Create from JSON

- **WHEN** a client posts a valid JSON questionnaire with `Content-Type: application/json` and both required headers
- **THEN** the service returns `201 Created` with JSON containing an absolute `url` and an RFC 3339 UTC `expires_at` timestamp

#### Scenario: Create from YAML

- **WHEN** a client posts the equivalent valid questionnaire with `Content-Type: application/yaml`
- **THEN** the service creates the same questionnaire structure and returns `201 Created`

#### Scenario: Unsupported or malformed input

- **WHEN** the content type is unsupported, the body is malformed, or either required header is absent
- **THEN** the service returns `415`, `400`, or `400` respectively and does not call Pushover

### Requirement: Questionnaire schema and limits

A questionnaire SHALL contain 1-20 questions. Each question SHALL have a non-empty `name` of at most 500 characters, `type` equal to `radio` or `checkbox`, and 2-50 distinct non-empty `answers` options of at most 200 characters each.

#### Scenario: Valid question types

- **WHEN** every question is a radio or checkbox question within the documented limits
- **THEN** schema validation accepts the questionnaire

#### Scenario: Unsupported fields or values

- **WHEN** input contains a free-text type, `confirm_reception`, an unknown field, too few or too many questions or options, duplicate options, or an over-limit string
- **THEN** the service returns `400` with a field-specific error and does not create a questionnaire

#### Scenario: Oversized request body

- **WHEN** a creation body exceeds 65,536 bytes before decoding
- **THEN** the service returns `413 Payload Too Large` and does not parse the body or call Pushover

### Requirement: Local recipient-key validation

The service SHALL validate `X-Pushover-User` as exactly 30 case-sensitive ASCII alphanumeric characters before calling Pushover. Syntactic validation SHALL NOT be represented as proof that the recipient exists.

#### Scenario: Malformed recipient key

- **WHEN** the recipient key contains an invalid character or has a length other than 30
- **THEN** the service returns `400`, does not call Pushover, and does not retain a questionnaire

### Requirement: Publication after Pushover acceptance

The service SHALL keep a new questionnaire unpublished while requesting notification. It SHALL publish only after Pushover returns HTTP 200 with `status: 1`, which means accepted and queued rather than delivered to a device.

#### Scenario: Pushover queues the notification

- **WHEN** Pushover accepts a valid notification with HTTP 200 and `status: 1`
- **THEN** the service makes the secret URL answerable and returns the successful creation response

#### Scenario: Recipient opens a racing link

- **WHEN** the answer URL is requested before Pushover acceptance has been processed
- **THEN** the service does not expose an answerable questionnaire before the publication transition

### Requirement: Failed notification cleanup

If Pushover rejects a request, is unavailable, times out, or returns an ambiguous result, the service SHALL NOT publish the questionnaire and SHALL delete its pending data. Recipient-specific rejection SHALL return `422`; other Pushover failures SHALL return `502`.

#### Scenario: Pushover rejects the recipient

- **WHEN** Pushover identifies the syntactically valid recipient key as invalid
- **THEN** the service deletes the pending questionnaire and returns `422` without publishing a URL

#### Scenario: Pushover outcome is unknown

- **WHEN** the Pushover request times out or the connection fails without an acceptance response
- **THEN** the service deletes the pending questionnaire and returns `502`, acknowledging that a previously sent notification may contain an inactive link

### Requirement: Secret capability URL

Each questionnaire SHALL have one cryptographically random, URL-safe token with at least 128 bits of entropy. Its absolute URL SHALL combine `public_address` with that token and SHALL authorize answering, retrieval, confirmation, and SSE streaming without another credential.

#### Scenario: URL is the only credential

- **WHEN** a caller presents the exact secret URL
- **THEN** the service permits the operation appropriate to the questionnaire state without requiring a questioner account or API token

#### Scenario: Unknown or deleted URL

- **WHEN** a caller presents an unknown, expired, or confirmed token
- **THEN** the service returns the same generic `404` response and does not reveal which case occurred

### Requirement: Pushover notification content

The notification SHALL identify the questioner, reference the first question and total question count, and carry the secret URL as Pushover's supplementary URL. Configured sound and non-emergency priority SHALL be applied without exposing the Pushover application token.

#### Scenario: Multiple-question notification

- **WHEN** a questionnaire contains more than one question
- **THEN** its Pushover message identifies the first question and states the total count rather than embedding the entire questionnaire

#### Scenario: Pushover length limits

- **WHEN** questioner or question text would exceed Pushover's title, message, URL-title, or URL limits
- **THEN** the service safely truncates display text to the documented Pushover limits while preserving the complete secret URL

### Requirement: Mobile-first answering page

A browser `GET` of an active secret URL SHALL render all questions using locally served UIkit and HTMX assets. The page SHALL be mobile-first, keyboard usable, and accessible with explicit labels and visible validation errors; no CDN or recipient login is required.

#### Scenario: Render on a narrow screen

- **WHEN** a recipient opens an active questionnaire on a mobile viewport
- **THEN** every question and option is readable and operable without horizontal scrolling, and radio or checkbox controls match their question types

#### Scenario: Assets are self-contained

- **WHEN** the answering page loads its styles and scripts
- **THEN** every UIkit and HTMX asset is served by Klaro and no third-party CDN request is required

### Requirement: Complete answer submission

Every question SHALL be required. A radio answer SHALL contain exactly one offered option; a checkbox answer SHALL contain one or more offered options. Invalid submissions SHALL leave the questionnaire answerable.

#### Scenario: Incomplete or forged answers

- **WHEN** a submission omits a question, supplies zero checkbox selections, supplies multiple radio selections, or includes an option not offered
- **THEN** the service returns `422`, identifies the invalid fields, and does not store a submission or close answering

#### Scenario: Valid submission

- **WHEN** every question has a valid answer
- **THEN** the service stores one answer array per question, preserves the selected option strings, and transitions the questionnaire to answered

### Requirement: First submission wins

The service SHALL atomically accept exactly one valid submission per questionnaire. This rule SHALL apply even when a Pushover group or several devices possess the same URL.

#### Scenario: Concurrent submissions

- **WHEN** two otherwise valid submissions race before either has completed
- **THEN** exactly one is stored and acknowledged, and the other receives `409 Conflict`

#### Scenario: Questionnaire already answered

- **WHEN** a recipient attempts another submission after answering closed
- **THEN** the service returns `409` and preserves the original answers unchanged

### Requirement: Full questionnaire retrieval

`GET` of the secret URL with `Accept: application/json` SHALL return status, expiry, question identifiers and definitions, and either `answers: null` or the stored answers. HTML-oriented requests SHALL receive HTML; event-stream requests follow the SSE requirements.

#### Scenario: Poll before answering

- **WHEN** a questioner requests JSON while no answer has been submitted
- **THEN** the service returns `200` with `status: "awaiting_answer"`, the questionnaire definitions, and `answers: null`

#### Scenario: Read after answering

- **WHEN** a questioner requests JSON after a submission
- **THEN** the service returns `200` with `status: "answered"` and the complete stored answers without deleting them

### Requirement: Answer-only polling

`GET` of the secret URL with `answer_only=1` SHALL return only status and answers as JSON. Polling SHALL be non-destructive and safe to repeat before or after submission.

#### Scenario: Answer is not ready

- **WHEN** `answer_only=1` is requested before submission
- **THEN** the service returns `200` with `{"status":"awaiting_answer","answers":null}`

#### Scenario: Answer is ready

- **WHEN** `answer_only=1` is requested after submission
- **THEN** the service returns `200` with `status: "answered"` and an object mapping question identifiers to answer arrays, without changing retention

### Requirement: Server-sent event stream

`GET` of an active secret URL with `Accept: text/event-stream` SHALL return an SSE stream, a five-second reconnection hint, and an immediate `status` event. Unknown, pending, expired, or deleted tokens SHALL NOT produce a successful stream.

#### Scenario: Connect while awaiting an answer

- **WHEN** a questioner opens the secret URL with `Accept: text/event-stream` before submission
- **THEN** the service returns `200` as `text/event-stream`, sends `retry: 5000`, and emits `status` with `awaiting_answer` and the original `expires_at`

#### Scenario: Stream transport protections

- **WHEN** the service starts an SSE response
- **THEN** it includes `Cache-Control: no-store` and `X-Accel-Buffering: no` and does not buffer events until the stream closes

### Requirement: SSE terminal state delivery

An SSE stream SHALL emit `answer` with the complete stored answers as soon as a submission occurs, or immediately if already answered, and then close. If expiry occurs while waiting, it SHALL emit `expired` and close without requiring another retrieval.

#### Scenario: Answer arrives while connected

- **WHEN** a valid submission is stored while a questioner is connected
- **THEN** the stream emits `answer` with `status: "answered"` and the complete answers object, then closes without a polling request

#### Scenario: Answer predates the connection

- **WHEN** a questioner opens SSE after an answer was stored
- **THEN** the service immediately emits the same terminal `answer` event with current answers and closes

#### Scenario: Questionnaire expires while connected

- **WHEN** the questionnaire reaches expiry before submission
- **THEN** the stream emits `expired`, closes, and subsequent connection attempts receive generic `404`

### Requirement: SSE heartbeats and reconnection

While a stream waits, the service SHALL emit a named `heartbeat` event with the current UTC time every `klaro.sse_heartbeat_seconds`, defaulting to 15 seconds. Reconnected clients SHALL receive current state rather than a replay of historical events.

#### Scenario: Heartbeat proves liveness

- **WHEN** no state transition occurs for one configured heartbeat interval
- **THEN** the client receives an observable `heartbeat` event containing a UTC timestamp and the stream remains open

#### Scenario: Interrupted stream reconnects

- **WHEN** a waiting connection drops and the client reconnects after the suggested five-second delay
- **THEN** the service emits current status or the terminal answer if submission occurred meanwhile, without requiring missed heartbeats to be replayed

#### Scenario: Heartbeats do not extend retention

- **WHEN** a questionnaire remains connected through repeated heartbeats beyond its expiry
- **THEN** heartbeats do not extend its deadline and the stream terminates through the expiry behavior

### Requirement: Explicit reception confirmation

The service SHALL delete an answered questionnaire only when it receives `POST` to the secret URL with `confirmed=1`. Confirmation before submission SHALL NOT delete an active questionnaire.

#### Scenario: Confirm an answer

- **WHEN** a questioner posts `confirmed=1` after retrieving or otherwise learning of a submission
- **THEN** the service permanently deletes the questionnaire and answer and returns `200` with `status: "confirmed"`

#### Scenario: Confirm too early or twice

- **WHEN** confirmation is requested before submission, or repeated after successful confirmation
- **THEN** the service returns `409` for the premature request or generic `404` for the repeated request, respectively

### Requirement: Configurable lifetime

Every questionnaire SHALL expire at `created_at` plus `klaro.lifetime_seconds`, whose default SHALL be 86,400 seconds. Reading, answering, retrieving, heartbeats, or SSE streaming SHALL NOT extend this deadline.

#### Scenario: Expire before or after answering

- **WHEN** the configured lifetime elapses while a questionnaire is active or answered but unconfirmed
- **THEN** the service permanently deletes all its data and subsequent use of its URL returns generic `404`

#### Scenario: Cleanup without polling

- **WHEN** nobody accesses an expired questionnaire
- **THEN** scheduled cleanup still deletes it within 60 seconds after its expiry

### Requirement: Persistent questionnaire state

Published questionnaires and their answers SHALL survive a normal process restart in `klaro.data_dir`. Restart SHALL NOT reset creation timestamps or extend expiry, and interrupted pending notifications SHALL NOT become published during recovery.

#### Scenario: Restart after answering

- **WHEN** Klaro restarts while an answered questionnaire awaits confirmation
- **THEN** the original answers and expiry remain available for retrieval and confirmation

### Requirement: Configuration validation

The service SHALL require Pushover `app_token`, `klaro.data_dir`, and an absolute `klaro.public_address`. It SHALL default `klaro.listen` to `127.0.0.1:3344`, `klaro.lifetime_seconds` to 86400, `klaro.sse_heartbeat_seconds` to 15, Pushover sound to `pushover`, and priority to 0.

#### Scenario: Invalid startup configuration

- **WHEN** mandatory configuration is absent, storage is unusable, lifetime or heartbeat interval is not positive, or priority is outside the supported non-emergency range `-2` through `1`
- **THEN** startup fails with a clear configuration error rather than running with partial behavior

### Requirement: Sensitive-data handling

The service SHALL NOT expose Pushover application tokens, recipient keys, or secret questionnaire tokens in application logs, error bodies, answer JSON, or notification metadata other than the intended secret URL itself.

#### Scenario: Upstream failure is logged

- **WHEN** a Pushover request fails and diagnostic information is recorded
- **THEN** logs and the client error contain actionable non-secret details but no application token, recipient key, or questionnaire token
