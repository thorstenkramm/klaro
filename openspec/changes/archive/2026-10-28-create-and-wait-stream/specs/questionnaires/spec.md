# Spec Delta

## MODIFIED Requirements

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

## ADDED Requirements

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
