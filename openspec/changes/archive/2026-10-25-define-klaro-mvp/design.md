# Design

## Context

See `proposal.md` for motivation and the two capability deltas for observable behavior. This is a greenfield Python service: there is no existing application, database, framework, or deployed API to preserve. The README examples are therefore documentation inputs, not compatibility constraints. The implementation must coordinate Pushover calls, persistent short-lived state, browser answering, and in-memory abuse controls within one instance and one Gunicorn worker.

## Goals / Non-Goals

**Goals:**

- Keep deployment and operation understandable with a small synchronous WSGI stack and no infrastructure beyond a filesystem directory.
- Make every lifecycle transition atomic and every HTTP response deterministic under concurrent requests.
- Bound outbound Pushover concurrency and network waits while preserving the accepted-and-queued publication rule.
- Make parsing, state transitions, clocks, and Pushover transport replaceable in tests.
- Serve a secure, self-contained mobile page without exposing bearer URLs through third-party requests.

**Non-Goals:**

- No database, message queue, distributed cache, asynchronous notification worker, or horizontal coordination.
- No admin interface, account system, delivery receipts, analytics, or general-purpose form builder.
- No compatibility promise for the README's illustrative JSON shape, GET-based confirmation, or `Content-Type`-based response negotiation.

## Decisions

### 1. Use a small synchronous Python stack

Use Python 3.11+, Flask and Jinja for HTTP and HTML, PyYAML's safe loader for YAML, `requests.Session` for Pushover, and Gunicorn's gevent worker for production. Use `pyproject.toml` and a committed `uv.lock` for reproducible installation.

Flask fits the route count, server-rendered UI, and streaming responses without Django's unused subsystems. FastAPI would add an ASGI stack and is unnecessary for this small form-based service. A standard-library WSGI implementation would make routing, request parsing, and templates needlessly manual.

Run exactly one gevent worker with a bounded connection pool, proposed as Gunicorn's 1,000-connection default. Greenlets allow long-lived SSE streams, a slow Pushover request, and ordinary traffic to coexist without dedicating an OS thread to each stream. Apply gevent monkey patching at the worker entry point before importing application modules, use gevent-compatible locks and conditions, and keep file operations short. Multiple worker processes remain unsupported.

### 2. Publish an explicit, small HTTP contract

Assign question identifiers `q1` through `q20` in input order. Keep answer arrays for both types so clients have one answer shape.

Creation success is:

```json
{
  "url": "https://klaro.example.com/<token>",
  "expires_at": "2026-10-26T12:00:00Z"
}
```

Full JSON retrieval contains `status`, `expires_at`, `questions`, and `answers`. Each question contains `id`, `name`, `type`, and its offered `answers`. Before submission, `answers` is null; afterward it maps question IDs to selected option arrays. `answer_only=1` omits everything except `status` and `answers`.

| Operation | Success | Main errors |
| --- | --- | --- |
| `POST /` | `201` creation JSON | `400`, `403`, `413`, `415`, `422`, `429`, `502` |
| `GET /<token>` | `200` HTML, full JSON, or SSE | generic `404` |
| `POST /<token>` | `200` answer HTML | `404`, `409`, `422` |
| `GET /<token>?answer_only=1` | `200` answer-only JSON | generic `404` |
| `POST /<token>?confirmed=1` | `200` confirmation JSON | `404`, `409` |

Use `Accept: application/json`, `Accept: text/html`, or `Accept: text/event-stream` rather than a GET request's `Content-Type` to select the representation. Native `EventSource` automatically selects SSE on the same secret URL. Require POST for submission and confirmation so prefetching a URL never mutates state. Rewrite the README examples accordingly.

API errors use this shape, with field details only when safe and useful:

```json
{
  "error": {
    "code": "invalid_request",
    "message": "The questionnaire is invalid.",
    "fields": {"questions.0.answers": ["Select at least two options."]}
  }
}
```

Use stable codes for rate limiting (`rate_limited`), recipient backoff (`recipient_backoff`), recipient rejection (`recipient_rejected`), upstream failure (`pushover_unavailable`), and confirmation or submission conflicts (`state_conflict`). Unknown, expired, and deleted tokens all use the same `not_found` response.

#### SSE framing and terminal events

An SSE connection begins with `retry: 5000` and an immediate current-state event. While waiting, the stream emits named events rather than comment-only heartbeats so both intermediaries and clients can observe liveness:

```text
event: status
data: {"status":"awaiting_answer","expires_at":"2026-10-26T12:00:00Z"}

event: heartbeat
data: {"time":"2026-10-25T12:00:15Z"}

event: answer
data: {"status":"answered","answers":{"q1":["beer"]}}
```

Use `expired` with `{"status":"expired"}` when the deadline arrives before submission. Heartbeats carry no event ID and do not extend retention. Answer and expiry are terminal: send the complete event, flush, and end the response. Clients must close native `EventSource` after a terminal event to prevent its automatic reconnect. On an interrupted waiting connection, reconnect to the same URL and send current state; no historical event replay or `Last-Event-ID` store is needed.

Return `Cache-Control: no-store` and `X-Accel-Buffering: no`, flush every event, and document equivalent buffering and read-timeout settings for other proxies. The configurable `klaro.sse_heartbeat_seconds` defaults to 15 seconds.

### 3. Model all operations as explicit state transitions

```text
pending -- Pushover accepted --> awaiting_answer -- valid submission --> answered
   |                                   |                               |
   | Pushover failure                  | expiry                        | expiry
   v                                   v                               v
deleted                             deleted                         deleted
                                       ^                               |
                                       |                               | confirmed=1
                                       +-------------------------------+
```

The final arrow summarizes answered-state deletion; active questionnaires cannot be confirmed early. Every operation checks expiry before checking or changing state. Unknown and already-deleted files are indistinguishable.

Creation persists `pending` before the outbound call, but pending URLs return generic `404`. Acceptance atomically changes the file to `awaiting_answer`; failure removes it. Submission changes `awaiting_answer` to `answered` only if the file remains active and unexpired. Confirmation removes only an `answered` file.

Maintain a worker-local subscriber condition for each token with waiting SSE streams. Notify subscribers only after the corresponding atomic answer or expiry transition commits. Registration and the initial state read use the same per-token lock, followed by a state recheck after subscription, so a transition between loading and listening cannot be missed. Wait on the condition with a heartbeat-timeout interval and re-read state on notification. A restart may disconnect streams; reconnection reads the persisted current state.

On startup, remove stale `pending` files because their outbound result is unknown and they were never published. Recover active and answered files using their stored timestamps; never resume a Pushover request automatically.

### 4. Use atomic per-questionnaire JSON files

Generate tokens with `secrets.token_urlsafe(32)`, providing 256 bits of entropy and no filename-unsafe characters. Store each record at `data_dir/questionnaires/<token>.json`; never accept a caller-supplied filename.

A record contains a schema version, status, creation and expiry timestamps, questioner label, questions, answers, and optionally a non-secret Pushover request identifier for diagnostics. Keep the recipient key only in request memory, not in the persisted record. Use UTC RFC 3339 timestamps and the original creation time for expiry.

For each write:

1. Acquire that token's in-memory lock.
2. Re-read the current file and evaluate expiry and state.
3. Write a same-directory temporary file with mode `0600`, flush and `fsync` it.
4. Atomically replace the target with `os.replace` and `fsync` the directory.
5. Release the lock. Confirmation and expiry unlink under the same lock.

Create storage directories with mode `0700`. A lock registry and all registry mutations require a small global lock, but network and file I/O do not run under that global lock. Atomic replacement lets readers see either complete version, while per-token locks serialize read-modify-write transitions. No file-locking protocol is promised across processes.

A filesystem is sufficient at this scale and directly satisfies the configured `data_dir`. SQLite would give stronger transaction tooling but adds a database abstraction without removing the single-instance restriction.

### 5. Enforce expiry lazily and with a worker-owned scheduler

Check expiry on every load and delete expired records before responding. Also run a cleanup pass every 30 seconds, guaranteeing deletion within the required 60 seconds without depending on polling. Notify waiting SSE subscribers after expiry commits so they receive the terminal event. Start this scheduler once in the sole worker, not in the Gunicorn master or application module import path.

Use wall-clock UTC for persisted deadlines and monotonic time for in-memory windows and delays. Tests use injected clocks. Operators should synchronize the host clock because wall-clock corrections can otherwise affect expiry.

### 6. Isolate Pushover behind a non-retrying adapter

Build a plain-text Pushover message with the questioner, first question, total count, configured sound and priority, supplementary answer URL, and URL title. Truncate display text to Pushover's 250-character title, 1,024-character message, and 100-character URL-title limits. Never truncate the URL; reject startup configuration whose base URL cannot produce a supplementary URL within 512 characters.

Use TLS verification, explicit connect and read timeouts, and at most two concurrent outbound requests through a worker-local semaphore. Accept only HTTP 200 with JSON `status: 1` as success. Classify a rejection as recipient-specific only from Pushover's structured user error; quota, application-token, other 4xx, 5xx, malformed responses, timeouts, and connection errors are not recipient backoff triggers.

Do not automatically retry notification POSTs. A timeout may occur after Pushover accepted the message, and retrying could create duplicate notifications or publish a second URL. Instead delete the pending record and return `502`, documenting that a dead-link notification is possible. The caller may create a fresh questionnaire. Sanitize logs and never serialize the outbound token or recipient key.

### 7. Implement abuse controls with deterministic in-memory algorithms

Resolve the client IP before creation validation. By default use the direct peer. `klaro.trusted_proxies` accepts IP addresses or CIDR ranges; only for those immediate peers, read the client address supplied by the trusted proxy. Operators must configure the proxy to overwrite incoming forwarding headers. Ignore forwarding headers from all other peers.

Protect rate state with its own lock. For each IP, store the monotonic window start and attempt count:

- If 60 seconds have elapsed, start a new window.
- Increment the count for every `POST /`, including requests that will be rejected.
- Counts one through five proceed; later counts return `429` without changing the window start.
- `Retry-After` is the ceiling of the remaining window time. Remove stale window entries after they expire.

Store recipient-backoff state separately per IP. The first structured recipient rejection sets a 60-second delay; each later recipient rejection after an allowed attempt doubles the previous delay, capped at 3600 seconds. Blocked attempts do not alter backoff. Only Pushover acceptance resets the level. Other failures leave it unchanged. If rate limiting and backoff both apply, return one `429` using the longer delay and the appropriate error code.

These controls intentionally reset on restart. The implementation does not claim accurate limits across processes or hosts.

### 8. Build the UI as a local progressive form

Vendor pinned UIkit and HTMX distributions in the Python package and serve them from same-origin static routes. Render semantic fieldsets and labels with Jinja, using repeated form fields named by question ID for checkbox values. HTMX submits the form and swaps the response fragment; a normal form POST remains a usable fallback.

On validation failure, re-render with entered values and field errors while retaining `awaiting_answer`. On success, render a read-only confirmation. Later browser visits show the stored answers and that answering is closed.

Send questionnaire pages and API responses with `Cache-Control: no-store`, `Referrer-Policy: no-referrer`, `X-Content-Type-Options: nosniff`, and a restrictive content-security policy permitting only same-origin assets. No external fonts, images, scripts, or links are needed. Redact token paths from application and access logs, and do not place tokens in query parameters.

### 9. Validate configuration before serving traffic

Load TOML with `tomllib` through an application factory. The supported shape is:

```toml
[pushover]
app_token = "<30-character-token>"
sound = "pushover"
priority = 0

[klaro]
data_dir = "/var/lib/klaro/data"
public_address = "https://klaro.example.com"
listen = "127.0.0.1:3344"
lifetime_seconds = 86400
sse_heartbeat_seconds = 15
# questioners = ["Your dinner mate"]
# trusted_proxies = ["127.0.0.1", "10.0.0.0/8"]
```

Omitting `questioners` permits all valid labels; an empty list denies all. Omitted `trusted_proxies` means no forwarded headers are trusted. Validate app-token shape, storage writability, absolute public URL, positive lifetime and SSE heartbeat interval, listen address, allowlist types, proxy ranges, and priority `-2` through `1` before the worker accepts requests.

Gunicorn and the application factory must read the same selected configuration file so `listen` cannot silently diverge from application settings. Development may use Flask directly, but production documentation provides only the one-worker Gunicorn command.

### 10. Design tests around boundaries rather than Pushover or the real clock

Use unit tests for JSON/YAML parity, duplicate keys, schema limits, safe YAML tags, recipient validation, message truncation, response shapes, and SSE frame encoding. Use injected clocks for fixed windows, backoff, expiry, and heartbeat scheduling. Use a mocked Pushover transport for acceptance, structured recipient rejection, quota errors, malformed responses, timeouts, and ambiguous failures.

Integration tests cover every spec scenario, restart recovery, stale-pending cleanup, HTML/JSON/SSE negotiation, non-destructive polling, and POST-only confirmation. Streamed-response tests cover initial status, heartbeat timing, answer and expiry terminal events, already-answered connections, reconnects, and registration races. Concurrency tests prove first-submission-wins, confirmation-versus-read behavior, and ordinary request progress while many SSE streams remain open. Browser checks at narrow and desktop viewports verify labels, keyboard operation, HTMX and non-HTMX submission, local assets, and absence of third-party requests.

## Risks / Trade-offs

- [The shared URL authorizes every operation] -> Use high entropy, no-store and no-referrer responses, log redaction, generic 404s, and clear documentation; this remains a deliberate bearer-capability trade-off.
- [Questioner labels are spoofable and creation is unauthenticated] -> Keep exact filtering and abuse controls, recommend trusted-network deployment when possible, and do not describe filtering as authentication.
- [A Pushover timeout can produce a dead-link notification] -> Never auto-retry, delete pending state, return a clear `502`, and let the caller issue a fresh questionnaire.
- [Accepted and queued does not mean delivered] -> Keep all API and user wording precise; no delivery SLA is claimed.
- [Group recipients race for one answer] -> Serialize transitions per token and return `409` to every submission after the first.
- [One worker constrains availability and capacity] -> Bound gevent connections, outbound calls, and timeouts; scaling requires a later shared-state redesign rather than adding workers.
- [Long-lived SSE can exhaust connections or be hidden by proxy buffering] -> Bound worker connections, flush named heartbeats, disable proxy buffering, and test ordinary request progress with open streams.
- [A transition can race SSE subscriber registration] -> Register and recheck under the per-token lock, then publish current state after every committed answer or expiry transition.
- [Filesystem corruption or disk failure can lose answers] -> Use atomic writes, restrictive permissions, startup checks, and operational backups only if the short-lived data warrants them.
- [Unauthenticated clients can grow in-memory IP state] -> Prune expired windows and idle backoff entries, and use reverse-proxy connection/request limits for exposed deployments.
- [YAML has richer parsing behavior than JSON] -> Enforce the byte limit, safe loading, strict scalar/container schemas, and reject duplicate or unknown keys.
- [Clock adjustments can change effective lifetime] -> Use UTC persisted timestamps, monotonic in-memory timers, and host time synchronization.

## Migration Plan

There is no existing implementation or stored data to migrate. Initial rollout consists of installing the package and vendored assets, creating a protected data directory, supplying TOML and Pushover credentials, configuring any trusted proxy and disabling SSE response buffering, and starting one gevent worker. Update README examples before announcing the API.

Rollback is to stop the new service and remove its deployment configuration. Preserve the data directory during rollback if unexpired answers matter. Never run old and new instances, two workers, or two hosts against the same directory.
