# Spec Delta

## MODIFIED Requirements

### Requirement: Configuration validation

The service SHALL require Pushover `app_token`, `klaro.data_dir`, and an absolute `klaro.public_address` without a path, query, or fragment. It SHALL default `klaro.listen` to `127.0.0.1:3344`, `klaro.lifetime_seconds` to 86400, `klaro.sse_heartbeat_seconds` to 15, Pushover sound to `pushover`, and priority to 0.

#### Scenario: Invalid startup configuration

- **WHEN** mandatory configuration is absent, storage is unusable, lifetime or heartbeat interval is not positive, or priority is outside the supported non-emergency range `-2` through `1`
- **THEN** startup fails with a clear configuration error rather than running with partial behavior

#### Scenario: Public address with a path

- **WHEN** `klaro.public_address` contains a path such as `https://example.org/klaro`
- **THEN** startup fails with a configuration error stating that Klaro must be served from the root of its host name, while a bare trailing slash is accepted and removed

## ADDED Requirements

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
