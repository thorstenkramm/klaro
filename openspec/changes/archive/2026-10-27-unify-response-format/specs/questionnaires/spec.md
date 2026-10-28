# Spec Delta

## MODIFIED Requirements

### Requirement: Questionnaire schema and limits

A questionnaire SHALL contain 1-20 questions with unique names compared as exact, case-sensitive strings. Each question SHALL have a non-empty `name` of at most 500 characters, `type` equal to `radio` or `checkbox`, and 2-50 distinct non-empty `answers` options of at most 200 characters each.

#### Scenario: Valid question types
- **WHEN** every question is a radio or checkbox question within the documented limits and names are unique
- **THEN** schema validation accepts the questionnaire

#### Scenario: Unsupported fields or values
- **WHEN** input contains a free-text type, `confirm_reception`, an unknown field, too few or too many questions or options, duplicate options, or an over-limit string
- **THEN** the service returns `400` with a field-specific error and does not create a questionnaire

#### Scenario: Oversized request body
- **WHEN** a creation body exceeds 65,536 bytes before decoding
- **THEN** the service returns `413 Payload Too Large` and does not parse the body or call Pushover

#### Scenario: Duplicate question name
- **WHEN** a question repeats an earlier question's exact name
- **THEN** creation returns `400 invalid_request` with `fields["questions.<index>.name"]` equal to `["Question names must be unique."]` for the later zero-based index, without calling Pushover or retaining a record

#### Scenario: Names differing in case or whitespace
- **WHEN** otherwise valid names differ only in case or surrounding whitespace
- **THEN** they are treated as distinct and preserved without normalization

### Requirement: Complete answer submission

Every question SHALL be required. Form selections SHALL use canonical decimal 1-based option indices, mapped to the exact offered strings. Radio questions SHALL accept exactly one index; checkbox questions SHALL accept one or more distinct indices. Invalid submissions SHALL return `422` with field errors and leave the questionnaire answerable.

#### Scenario: Incomplete or forged answers
- **WHEN** a submission omits a question, supplies zero checkbox selections, supplies multiple radio selections, repeats an index, supplies an unknown field, or uses an invalid or out-of-range index
- **THEN** the service returns `422`, identifies the invalid fields, and does not store a submission or close answering

#### Scenario: Valid submission
- **WHEN** every question has valid indices
- **THEN** the service stores one answer array per question containing exact source option strings in submitted order, transitions to answered, and atomically records `answered_at` as the current UTC time

#### Scenario: Noncanonical indices
- **WHEN** a submitted value is `0`, `01`, `+1`, `1.0`, whitespace-padded, non-ASCII digits, or outside the offered range
- **THEN** it is rejected with `422` rather than coerced into an option index

#### Scenario: Text resembling an index
- **WHEN** the offered strings are `["2", "1"]` and the submitted index is `1`
- **THEN** the stored and returned selected string is `"2"`

#### Scenario: Validation preserves valid selections
- **WHEN** part of an HTML or HTMX submission is invalid
- **THEN** the `422` response preserves valid index selections and their visible option labels for correction

### Requirement: Full questionnaire retrieval

JSON retrieval SHALL return exactly `expires_at`, `answered_at`, and ordered `questions`. Each question SHALL contain `name`, `type`, offered `answers`, selected `answered`, `other`, `comment`, and `recommendations`. It SHALL omit IDs, `status`, top-level `answers`, `created_at`, and `questioner`. HTML-oriented requests SHALL receive HTML; event-stream requests follow the SSE requirements.

#### Scenario: Poll before answering
- **WHEN** a questioner requests JSON before submission
- **THEN** the response is `200` with `answered_at: null`, the original expiry, question definitions in creation order, and `answered: null`, `other: null`, `comment: null`, and `recommendations: []` on every question

#### Scenario: Read after answering
- **WHEN** a questioner requests JSON after submission
- **THEN** the response is `200` with the persisted RFC 3339 UTC `answered_at`, original expiry, exact selected strings in each question's `answered` array, and the same extension defaults, without deleting data or changing timestamps

### Requirement: Answer-only polling

`GET` with `answer_only=1` SHALL return exactly `answered_at` and ordered `questions`. Each question SHALL contain exactly `name`, `answered`, `other`, `comment`, and `recommendations`, using the same values as full retrieval. Polling SHALL be non-destructive and safe to repeat before or after submission.

#### Scenario: Answer is not ready
- **WHEN** `answer_only=1` is requested before submission
- **THEN** the service returns `200` with `answered_at: null` and each question's name, `answered: null`, `other: null`, `comment: null`, and `recommendations: []`

#### Scenario: Answer is ready
- **WHEN** `answer_only=1` is requested after submission
- **THEN** the service returns `200` with the original answer timestamp and per-question selected strings, without changing retention or deleting data

### Requirement: Server-sent event stream

`GET` of an active secret URL with `Accept: text/event-stream` SHALL return an SSE stream, a five-second reconnection hint, and an immediate `status` event containing `answered_at: null`, `expires_at`, and the absolute secret `url`. Unknown, pending, expired, or deleted tokens SHALL NOT produce a successful stream. Already answered questionnaires SHALL follow terminal answer delivery instead.

#### Scenario: Connect while awaiting an answer
- **WHEN** a questioner opens the secret URL with `Accept: text/event-stream` before submission
- **THEN** the service returns `200` as `text/event-stream`, sends `retry: 5000`, and emits `status` containing exactly `answered_at: null`, the original `expires_at`, and the same absolute `url` as creation

#### Scenario: Stream transport protections
- **WHEN** the service starts an SSE response
- **THEN** it includes `Cache-Control: no-store` and `X-Accel-Buffering: no` and does not buffer events until the stream closes

#### Scenario: Reconnect while waiting
- **WHEN** a client reconnects while the questionnaire is still awaiting an answer
- **THEN** the new `status` event includes the same absolute URL and original expiry, without replaying historical events

### Requirement: SSE terminal state delivery

An SSE stream SHALL emit `answer` with a payload identical to answer-only polling as soon as a submission occurs, or immediately if already answered, and then close. If expiry occurs while waiting, it SHALL emit `expired` containing exactly the original `expires_at` and close without requiring another retrieval.

#### Scenario: Answer arrives while connected
- **WHEN** a valid submission is stored while a questioner is connected
- **THEN** the stream emits `answer` with the persisted `answered_at` and per-question answer-only representation, then closes without a polling request

#### Scenario: Answer predates the connection
- **WHEN** a questioner opens SSE after an answer was stored
- **THEN** the service immediately emits the same terminal `answer` payload as polling and closes without emitting an awaiting-answer `status` event

#### Scenario: Questionnaire expires while connected
- **WHEN** the questionnaire reaches expiry before submission
- **THEN** the stream emits `expired` with `{"expires_at":"<original RFC 3339 UTC deadline>"}`, even if cleanup already deleted the record, closes, and subsequent connection attempts receive generic `404`

### Requirement: Persistent questionnaire state

Published questionnaires, their answers, and `answered_at` SHALL survive a normal process restart in `klaro.data_dir`. Restart SHALL NOT reset creation or answer timestamps or extend expiry, and interrupted pending notifications SHALL NOT become published during recovery.

#### Scenario: Restart after answering
- **WHEN** Klaro restarts while an answered questionnaire awaits confirmation
- **THEN** the original answers, `answered_at`, and expiry remain available for retrieval, SSE delivery, and confirmation

#### Scenario: First submission fixes the answer timestamp
- **WHEN** two valid submissions race or a later submission is attempted
- **THEN** exactly one answer set and its timestamp persist atomically, and a losing submission receives `409` without altering either value

### Requirement: Sensitive-data handling

The service SHALL NOT expose application tokens, recipient keys, or secret questionnaire tokens in logs, error bodies, or answer JSON. The intended secret URL SHALL be exposed only through creation responses, the Pushover supplementary URL, and SSE `status` events to callers already possessing the URL.

#### Scenario: Upstream failure is logged
- **WHEN** a Pushover request fails and diagnostic information is recorded
- **THEN** logs and the client error contain actionable non-secret details but no application token, recipient key, or questionnaire token

#### Scenario: URL in status is not in answer data
- **WHEN** a client receives an SSE `status` event and later receives answer data
- **THEN** only the `status` payload includes the secret URL; full JSON, answer-only JSON, and SSE `answer` exclude it, and application and access logs remain redacted
