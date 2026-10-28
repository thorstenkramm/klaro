# questionnaires Specification

## Purpose

Provides a complete, short-lived questionnaire lifecycle from an API client's request through Pushover notification, one mobile-friendly response, live answer streams, non-destructive retrieval, explicit acknowledgement, and deletion.

## Requirements

### Requirement: Questionnaire creation contract

The service SHALL accept `POST /` with `X-Pushover-User`, `X-Questioner`, and a `questions` array in JSON or YAML. After publication it SHALL return `201` JSON with the absolute URL and expiry, unless the client explicitly prefers `text/event-stream`, in which case it SHALL return an empty `303` with same-origin relative `Location: /<token>`. Creation failures SHALL remain JSON errors without redirects.

#### Scenario: Create from JSON
- **WHEN** a client posts valid JSON with both required headers without preferring SSE
- **THEN** the service returns `201 Created` with absolute `url` and RFC 3339 UTC `expires_at`

#### Scenario: Create from YAML
- **WHEN** a client posts equivalent valid YAML without preferring SSE
- **THEN** the service creates the same questionnaire structure and returns `201 Created`

#### Scenario: Unsupported or malformed input
- **WHEN** the content type is unsupported, the body is malformed, or either required header is absent
- **THEN** the service returns `415`, `400`, or `400` respectively and does not call Pushover

#### Scenario: Create and follow to the stream
- **WHEN** a valid creation explicitly prefers `text/event-stream` and Pushover accepts publication
- **THEN** the response is `303`, has a zero-length body and relative `Location: /<token>`, and following as GET with the same Accept header uses the existing SSE contract

#### Scenario: SSE negotiation is explicit
- **WHEN** Accept is absent, wildcard-only, gives event-stream quality zero, or prefers JSON/HTML equally or more strongly
- **THEN** successful creation returns `201` JSON rather than a redirect

#### Scenario: SSE creation failure
- **WHEN** creation with SSE Accept fails validation, allowlisting, rate limiting, recipient delivery or upstream availability
- **THEN** the original JSON error status and applicable Retry-After are returned without Location, publication or a stream

#### Scenario: Redirect cannot change origin
- **WHEN** a creation request uses a hostile Host header or the configured public address differs from the request origin
- **THEN** Location remains `/<token>` without scheme, authority or request-controlled content

### Requirement: Questionnaire schema and limits

A questionnaire SHALL contain 1-20 questions with exact case-sensitive unique names. Each SHALL have a nonempty name up to 500 characters, radio or checkbox type, and 2-50 distinct nonempty options up to 2,000 characters. Optional allow_other and allow_comments SHALL be booleans defaulting to false. Optional recommendations SHALL be unique integer 1-based offered-option indices, defaulting to empty. Each option SHALL begin with a nonempty paragraph.

#### Scenario: Valid question types
- **WHEN** questions have supported types, unique names, valid flags and recommendations, and text-first options within source limits
- **THEN** creation accepts the questionnaire

#### Scenario: Unsupported fields or values
- **WHEN** input contains a free-text question type, confirm_reception, unknown fields, duplicate source options, invalid counts, over-limit source strings, nonboolean flags or invalid recommendations
- **THEN** creation returns `400 invalid_request` with field-specific errors and no notification or retained record

#### Scenario: Oversized request body
- **WHEN** a creation body exceeds 65,536 bytes before decoding, even with individually valid option lengths
- **THEN** creation returns `413` without parsing it or calling Pushover

#### Scenario: Duplicate question name
- **WHEN** a question repeats an earlier exact source name
- **THEN** creation returns `400 invalid_request` with `fields["questions.<index>.name"]` equal to `["Question names must be unique."]` for the later zero-based index without notification or retained data

#### Scenario: Names differing in case or whitespace
- **WHEN** source names differ only in case or surrounding whitespace
- **THEN** they remain distinct and are preserved without normalization

#### Scenario: Option source length boundaries
- **WHEN** a text-first option has 2,000 or 2,001 characters within the creation body limit
- **THEN** 2,000 is accepted and 2,001 returns `400` at `questions.<question-index>.answers.<option-index>`

#### Scenario: Code-first option
- **WHEN** an option begins, after blank lines, with a fenced or indented code block and has no preceding paragraph
- **THEN** creation returns `400 invalid_request` at its zero-based option field with no notification or retained record

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

The notification SHALL identify the questioner, reference the first question and total count, and carry the secret supplementary URL. Supported inline Markdown in the first question SHALL become plain text before truncation; unsupported syntax SHALL remain literal. Configured sound and non-emergency priority SHALL apply without exposing the application token.

#### Scenario: Multiple-question notification
- **WHEN** a questionnaire has multiple questions
- **THEN** the message includes the first question in plain text and the total count rather than the entire questionnaire

#### Scenario: Pushover length limits
- **WHEN** text exceeds Pushover limits
- **THEN** display text is truncated after Markdown-to-text conversion while the complete secret URL is preserved

#### Scenario: Inline formatting in notification
- **WHEN** the first question contains emphasis and inline code
- **THEN** the message contains their text without supported formatting delimiters or generated HTML

### Requirement: Mobile-first answering page

A browser `GET` of an active secret URL SHALL render all questions using locally served UIkit and HTMX assets. The page SHALL be mobile-first, keyboard usable, and accessible with explicit labels and visible validation errors; no CDN or recipient login is required.

#### Scenario: Render on a narrow screen

- **WHEN** a recipient opens an active questionnaire on a mobile viewport
- **THEN** every question and option is readable and operable without horizontal scrolling, and radio or checkbox controls match their question types

#### Scenario: Assets are self-contained

- **WHEN** the answering page loads its styles and scripts
- **THEN** every UIkit and HTMX asset is served by Klaro and no third-party CDN request is required

### Requirement: Complete answer submission

Every question SHALL require a selection. Offered choices SHALL use canonical ASCII decimal 1-based indices mapped to exact source strings. Enabled Other SHALL use `other`: radio accepts exactly one choice; checkbox accepts one or more distinct choices including Other. Invalid submissions SHALL return `422` field errors and leave answering open. Valid submissions SHALL atomically store offered choices, Other, comments and one UTC `answered_at`.

#### Scenario: Incomplete or forged answers
- **WHEN** submission omits a selection, repeats a choice, sends multiple radio choices, unknown fields, a disabled Other choice or invalid indices
- **THEN** the service returns `422` and stores nothing

#### Scenario: Valid submission
- **WHEN** all choices and enabled text fields are valid
- **THEN** exact offered strings in submitted order, normalized text and answered_at are stored together and answering closes

#### Scenario: Noncanonical indices
- **WHEN** an offered choice index is zero, padded, signed, fractional, non-ASCII or out of range
- **THEN** it is rejected with `422` rather than coerced

#### Scenario: Text resembling an index
- **WHEN** options are `["2", "1"]` and the submitted offered index is `1`
- **THEN** the selected source value is `"2"`

#### Scenario: Validation preserves valid selections
- **WHEN** an HTML or HTMX submission has an invalid field
- **THEN** its `422` page or fragment preserves valid selections and submitted text, and reopens comments containing text or errors

### Requirement: First submission wins

The service SHALL atomically accept exactly one valid submission per questionnaire. This rule SHALL apply even when a Pushover group or several devices possess the same URL.

#### Scenario: Concurrent submissions

- **WHEN** two otherwise valid submissions race before either has completed
- **THEN** exactly one is stored and acknowledged, and the other receives `409 Conflict`

#### Scenario: Questionnaire already answered

- **WHEN** a recipient attempts another submission after answering closed
- **THEN** the service returns `409` and preserves the original answers unchanged

### Requirement: Full questionnaire retrieval

Full JSON SHALL return exactly expires_at, answered_at and ordered questions, each containing name, type, offered answers, allow_other, allow_comments, answered, other, comment and recommendations. Recommendations SHALL contain sorted configured indices both before and after answering. IDs, status, created_at and questioner SHALL be omitted. HTML and SSE negotiation SHALL retain their existing behavior.

#### Scenario: Poll before answering
- **WHEN** full JSON is retrieved before submission
- **THEN** answered_at, answered, other and comment are null, flags reflect the definition, and recommendations contains sorted configured indices or an empty array

#### Scenario: Read after answering
- **WHEN** full JSON is retrieved after submission
- **THEN** it contains the unchanged recommendation metadata, original expiry, persisted timestamp and answers without mutating data or retention

### Requirement: Answer-only polling

Answer-only GET SHALL return exactly answered_at and ordered questions containing exactly name, answered, other, comment and recommendations. Recommendation indices SHALL match full JSON both before and after submission. All answer-only values SHALL match SSE answer data. Polling SHALL remain repeatable and non-destructive.

#### Scenario: Answer is not ready
- **WHEN** polling precedes submission
- **THEN** answered_at, answered, other and comment are null and recommendations contains the sorted configured indices

#### Scenario: Answer is ready
- **WHEN** polling follows submission
- **THEN** it returns the persisted timestamp, selections, normalized text and unchanged recommendation indices without modifying retention

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

Published definitions, choices, Other, comments and answered_at SHALL survive normal process restart. Restart SHALL NOT change timestamps or expiry. Pending interrupted notifications SHALL NOT become published. Exactly one complete winning submission SHALL persist atomically.

#### Scenario: Restart after answering
- **WHEN** an answered questionnaire with Other and comments is reloaded after restart
- **THEN** its flags, exact choices, texts, timestamp and expiry remain available for JSON, HTML, SSE and confirmation

#### Scenario: First submission fixes the answer timestamp
- **WHEN** valid submissions with different text race or a later submission is attempted
- **THEN** only the winning choices, texts and timestamp persist together and the loser receives `409`

### Requirement: Configuration validation

The service SHALL require Pushover `app_token`, `klaro.data_dir`, and an absolute `klaro.public_address` without a path, query, or fragment. It SHALL default `klaro.listen` to `127.0.0.1:3344`, `klaro.lifetime_seconds` to 86400, `klaro.sse_heartbeat_seconds` to 15, Pushover sound to `pushover`, and priority to 0.

#### Scenario: Invalid startup configuration

- **WHEN** mandatory configuration is absent, storage is unusable, lifetime or heartbeat interval is not positive, or priority is outside the supported non-emergency range `-2` through `1`
- **THEN** startup fails with a clear configuration error rather than running with partial behavior

#### Scenario: Public address with a path

- **WHEN** `klaro.public_address` contains a path such as `https://example.org/klaro`
- **THEN** startup fails with a configuration error stating that Klaro must be served from the root of its host name, while a bare trailing slash is accepted and removed

### Requirement: Sensitive-data handling

The service SHALL NOT expose application tokens, recipient keys, or secret questionnaire tokens in logs, error bodies, or answer JSON. The intended secret URL SHALL be exposed only through creation responses, the Pushover supplementary URL, and SSE `status` events to callers already possessing the URL.

#### Scenario: Upstream failure is logged
- **WHEN** a Pushover request fails and diagnostic information is recorded
- **THEN** logs and the client error contain actionable non-secret details but no application token, recipient key, or questionnaire token

#### Scenario: URL in status is not in answer data
- **WHEN** a client receives an SSE `status` event and later receives answer data
- **THEN** only the `status` payload includes the secret URL; full JSON, answer-only JSON, and SSE `answer` exclude it, and application and access logs remain redacted

### Requirement: Single-invocation stream client guidance

The documented curl workflow SHALL create and consume SSE with one invocation using `--location`, `--no-buffer`, and `--fail-with-body`, without forcing POST on redirects. It SHALL expose the effective URL after completion as well as the waiting status URL, so an immediate answer remains confirmable. Stream completion SHALL NOT implicitly confirm reception.

#### Scenario: Waiting curl journey
- **WHEN** the documented command creates a questionnaire that is answered after stream connection
- **THEN** it follows the 303 as GET, receives retry/status and the terminal answer or expiry, closes, and leaves an answered record available for explicit confirmation

#### Scenario: Answer wins the redirect race
- **WHEN** an answer is stored before the redirected GET starts
- **THEN** the stream sends retry and the terminal answer without a waiting status, and curl's documented effective-URL output still identifies the confirmation URL

#### Scenario: Curl reports a creation error
- **WHEN** the documented command receives a creation error
- **THEN** it returns a nonzero exit status and displays the JSON error body instead of waiting for SSE

### Requirement: Optional text answer semantics

Enabled Other and comment fields SHALL accept at most one submitted value each. Other SHALL trim surrounding whitespace and require nonempty text when selected; unselected Other text SHALL be ignored. Comments SHALL be optional, trimmed, and null when blank. Both normalized values SHALL be limited to 2,000 Unicode code points. Disabled text fields SHALL be rejected even when empty.

#### Scenario: Radio Other selection
- **WHEN** a radio question permits Other and only Other with valid text is selected
- **THEN** answered is `[]` and other contains trimmed text

#### Scenario: Checkbox Other selection
- **WHEN** an enabled checkbox Other is selected alone or alongside offered choices
- **THEN** the selection is complete and answered contains only offered choices while other contains the separate text

#### Scenario: Other needs a description
- **WHEN** Other is selected with missing or whitespace-only text
- **THEN** `422` includes `Describe your other answer.` at `<qid>-other`

#### Scenario: Disabled and repeated text fields
- **WHEN** a disabled `<qid>-other` or `<qid>-comment` field is submitted, or an enabled field has multiple submitted values
- **THEN** submission returns `422` with field errors rather than accepting ambiguous text

#### Scenario: Text field boundaries
- **WHEN** enabled normalized Other or comment text has 2,000 or 2,001 Unicode code points within the body cap
- **THEN** 2,000 is accepted and 2,001 returns `422` at that text field

#### Scenario: Comment does not answer a question
- **WHEN** a comment is submitted without any valid selection
- **THEN** submission returns `422` for the missing selection and preserves the comment

#### Scenario: Plain text rendering
- **WHEN** Other or comments contain HTML, Markdown, ampersands or line breaks
- **THEN** they are displayed as escaped plain text with line breaks preserved and returned as text, without executing markup

### Requirement: Mobile text entry controls

Enabled Other SHALL appear as the last option labeled Other with an associated textarea. Comments SHALL use native details/summary with an accessible icon control. Controls SHALL work by keyboard and without JavaScript at 320px with no page overflow, with visible focus and 44px targets. Read-only views SHALL identify Other and Your comment separately.

#### Scenario: Other and comment correction without scripts
- **WHEN** a no-JavaScript recipient opens comments, chooses Other, submits invalid text and corrects it
- **THEN** labels, errors, selections and entered text remain usable and the valid submission reaches the read-only view

#### Scenario: Text entry with HTMX
- **WHEN** a mobile recipient corrects a text field error through HTMX
- **THEN** the fragment keeps entered values and accessible field-error associations and a subsequent valid submission displays both text types correctly

### Requirement: Answer request body limits

Answer POST bodies SHALL have a 524,288-byte limit before decoding; creation and confirmation SHALL retain the 65,536-byte limit. Exceeding a limit SHALL return `413` without storing answers. The byte limit SHALL apply independently of character limits, including encoding overhead. HTMX answer errors SHALL leave the existing form and all entered values in place and show an accessible size error.

#### Scenario: Separate creation and answer caps
- **WHEN** a valid answer body is larger than 65,536 but no larger than 524,288 bytes
- **THEN** it reaches field validation, while a creation body of the same size returns `413`

#### Scenario: Aggregate Unicode body exceeds cap
- **WHEN** a URL-encoded answer exceeds 524,288 bytes even though each text field is within 2,000 characters
- **THEN** it returns `413` without accepting a partial answer; HTMX displays the size error without replacing or clearing the form

#### Scenario: Full-page oversized submission
- **WHEN** a non-HTMX answer exceeds the cap
- **THEN** it receives an understandable `413` response and the questionnaire remains answerable without parsing and echoing the oversized body

### Requirement: Dedicated recommendation metadata

Recommendations SHALL be accepted only through the recommendations key, with strictly integer indices excluding booleans, unique and within the offered option range. Invalid values SHALL return `400 invalid_request` at `questions.<index>.recommendations`. Stored and returned indices SHALL be sorted ascending and survive restart. Option strings SHALL remain unchanged; prefixes SHALL NOT imply recommendations.

#### Scenario: Multiple recommendations
- **WHEN** recommendations is `[4, 1]` for four options
- **THEN** stored, full JSON, polling and SSE metadata is `[1, 4]`, including after restart

#### Scenario: Invalid recommendation list
- **WHEN** recommendations is null, a scalar, contains duplicates, booleans, strings, floats, zero, negative or out-of-range indices
- **THEN** creation returns `400 invalid_request` at the recommendations field without notification or retained data

#### Scenario: Literal leading asterisks
- **WHEN** an option starts with `*` or a backslash and no recommendation list is supplied
- **THEN** it has no recommendation and the source string is retained exactly, including in answered values

#### Scenario: Other cannot be recommended
- **WHEN** recommendations refers to `other` or to an index beyond the offered options on an allow_other question
- **THEN** creation rejects the list even though Other is available as an answer

### Requirement: Recommendations are guidance without selection

Recommended choices SHALL display accessible Recommended tabs with petrol styling, while selected state remains orange. No recommendation SHALL preselect an input, satisfy required selection, or influence progress. When recommendations exist, the form SHALL state `Recommendations come from {questioner}. Nothing is preselected.` No per-question recommendation count or star icon SHALL be shown.

#### Scenario: Initial recommendation presentation
- **WHEN** a radio or checkbox question has recommendations
- **THEN** Recommended is included in each recommended choice's accessible label, all choices start unchecked and progress is zero

#### Scenario: Recipient chooses freely
- **WHEN** a recipient selects a recommended choice, another choice, or permitted Other
- **THEN** validation and storage follow the same selection rules, and choosing a recommendation shows orange selection while retaining its petrol tab

#### Scenario: Recommendations remain usable without JavaScript
- **WHEN** a recipient uses a 320px viewport or keyboard with scripts disabled
- **THEN** recommendation tabs and 44px choice targets remain usable without page overflow and nothing becomes preselected

### Requirement: Read-only recommendation presentation

Read-only views SHALL mark chosen recommended options with a Recommended badge. Recommended options that were not selected SHALL appear separately with a Recommended tab and `not chosen` text. These displays SHALL NOT modify the answered arrays or imply the recipient selected unchosen recommendations.

#### Scenario: Selected and unselected recommendations
- **WHEN** the recipient selects one of two recommended choices
- **THEN** the selected answer has its badge and the other appears in a separate not-chosen block, while JSON contains only the actual selected answers

#### Scenario: Other instead of a recommendation
- **WHEN** the recipient chooses only Other
- **THEN** read-only text shows Other as the answer and all recommended offered choices separately as not chosen

### Requirement: Restricted Markdown rendering

Names SHALL support strong emphasis, emphasis and inline code only. Options SHALL additionally support paragraphs, line breaks, fenced and indented code. Raw HTML, links, images, headings, lists, tables and quotes SHALL be displayed literally without active markup or external requests. Fenced syntax in names SHALL remain literal. Source strings SHALL remain unchanged in storage, full JSON, polling and SSE.

#### Scenario: Supported inline formatting
- **WHEN** a name or option contains strong emphasis, emphasis or inline code
- **THEN** the answering and read-only views display the corresponding formatting without changing the stored or returned source

#### Scenario: Unsupported and hostile syntax
- **WHEN** content includes raw script/HTML, a Markdown image or link, heading, list, table, quote or unsafe URL
- **THEN** it remains visible literal text, creates no active element or URL-bearing attribute and makes no external request

#### Scenario: Inline-only names
- **WHEN** a name contains fenced or indented block-like syntax
- **THEN** it is rendered as literal text rather than a code block, including literal fence delimiters

#### Scenario: Plain-text answer fields
- **WHEN** Other, comments or questioner text contain Markdown or HTML syntax
- **THEN** they remain escaped plain text and are not sent through the Markdown renderer

#### Scenario: Source fidelity and recommendation independence
- **WHEN** a recommended option containing Markdown is selected by index
- **THEN** every public answer returns its original source string and recommendations remain determined only by the dedicated metadata

### Requirement: Text-first option layout

An option's first paragraph SHALL be its clickable labeled head. Remaining paragraphs and code blocks SHALL appear underneath outside the label and be associated with the control as descriptive content. Code areas SHALL be keyboard-focusable and horizontally scroll internally; the page SHALL fit a 320px viewport. The same formatted content SHALL appear in selected answers and recommended-but-not-chosen views, without requiring scripts or inline styles.

#### Scenario: Paragraph and code option
- **WHEN** an option contains a text paragraph followed by code and further paragraphs
- **THEN** the first paragraph labels its index-valued input, subsequent content appears below, and selecting text in the code does not select the option

#### Scenario: Narrow keyboard and no-JavaScript view
- **WHEN** a 320px viewport displays a long code line with JavaScript disabled
- **THEN** the page has no horizontal overflow, the code box scrolls by keyboard, and the option remains selectable through its label

#### Scenario: Answered rich option
- **WHEN** a recipient submits a formatted option
- **THEN** the read-only view retains its formatting and code and the original source remains in JSON, including after restart

### Requirement: JSON error contract for malformed and unexpected failures

Creation bodies nested too deeply to parse SHALL be rejected as `400 invalid_request` without logging a parser traceback. Unexpected server errors SHALL return `500` with the JSON error code `internal_error` and no exception details, except to clients that explicitly prefer `text/html`.

#### Scenario: Deeply nested body

- **WHEN** a JSON or YAML creation body nests arrays or objects deeper than the parser can process
- **THEN** the service returns `400` with code `invalid_request` and does not call Pushover

#### Scenario: Unexpected server error

- **WHEN** an unexpected exception occurs for a client accepting `*/*` or `application/json`
- **THEN** the response is `500` with `{"error": {"code": "internal_error", "message": "An unexpected error occurred."}}` and contains no exception text

### Requirement: Unreadable stored records

A stored record that cannot be decoded or violates the record rules SHALL never be served: every route SHALL treat its token like an unknown token. The service SHALL log one warning per such file without its token and SHALL delete the file once `klaro.lifetime_seconds` have passed since its last modification.

#### Scenario: Unreadable record is not served

- **WHEN** a record file contains invalid JSON, another schema version, or content violating the current rules
- **THEN** retrieval, polling, SSE, answering, and confirmation return the same generic `404` as an unknown token

#### Scenario: Unreadable record is deleted after its lifetime

- **WHEN** cleanup or startup recovery encounters an unreadable record whose last modification is at least the configured lifetime ago
- **THEN** the file is deleted and the logs record the deletion without containing the token

### Requirement: Browser answer submission feedback

Answer submission SHALL be browser-only and respond with HTML pages or HTMX fragments; only an oversized answer form SHALL receive the HTML request-too-large page. After an HTMX swap, focus SHALL move to the error summary or the "Answer stored" heading, results SHALL be announced through a live region outside the swap target, and duplicate submissions SHALL be dropped.

#### Scenario: Validation errors receive focus

- **WHEN** an HTMX submission returns `422`
- **THEN** focus moves to the error summary, which has `role="alert"`, and the persistent live region is not duplicated

#### Scenario: Stored answer is announced

- **WHEN** an HTMX submission succeeds
- **THEN** focus moves to the "Answer stored" heading and the persistent live region announces "Answer stored"

#### Scenario: Duplicate submission is dropped

- **WHEN** the recipient submits again while a submission request is still in flight
- **THEN** the submit button is disabled, the additional submissions are dropped, and exactly one request is sent

#### Scenario: Oversized API request receives JSON

- **WHEN** an oversized creation or confirmation request, or an HTMX answer request, exceeds its body limit even with a browser `Accept` header
- **THEN** the service returns `413` with JSON code `payload_too_large`, while an oversized plain answer form receives the HTML request-too-large page
