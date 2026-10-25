# Klaro

Klaro adds a short-lived questionnaire back channel to Pushover notifications. A recipient opens the secret URL in a
browser and answers required radio and checkbox questions; the questioner retrieves or streams the structured result. No
recipient account or application is required.

## API journey

The examples use `https://klaro.example.com`; replace the recipient key with your 30-character Pushover user or group
key. The questioner label is a display/filtering label, not a credential.

### Create with JSON

<!-- example:json-create -->

```shell
curl -sS https://klaro.example.com/ \
  -H "Content-Type: application/json" \
  -H "X-Pushover-User: <your-key>" \
  -H "X-Questioner: Your dinner mate" \
  --data-binary @- <<'JSON'
{
  "questions": [
    {"name": "Drink?", "type": "radio", "answers": ["beer", "water"]},
    {"name": "Sides?", "type": "checkbox", "answers": ["rice", "salad"]}
  ]
}
JSON
```

Klaro publishes only after Pushover accepts and queues the notification. The `201 Created` response contains the
absolute capability URL and its UTC expiry:

<!-- example:creation-response -->

```json
{
  "url": "https://klaro.example.com/<token>",
  "expires_at": "2026-10-25T12:01:00Z"
}
```

### Create the equivalent questionnaire with YAML

<!-- example:yaml-create -->

```shell
curl -sS https://klaro.example.com/ \
  -H "Content-Type: application/yaml" \
  -H "X-Pushover-User: <your-key>" \
  -H "X-Questioner: Your dinner mate" \
  --data-binary @- <<'YAML'
questions:
  - name: Drink?
    type: radio
    answers: [beer, water]
  - name: Sides?
    type: checkbox
    answers: [rice, salad]
YAML
```

Each question has 2–50 offered options. A questionnaire has 1–20 questions; every question is required, and only `radio`
and `checkbox` are supported. Question IDs are assigned as `q1`, `q2`, and so on in input order.

### Retrieve the questionnaire or only its answers

Set `URL` to the complete secret URL returned by creation. Use `Accept`, not the request `Content-Type`, to negotiate
retrieval:

<!-- example:retrieve -->

```shell
curl -sS -H "Accept: application/json" "$URL"
```

Before submission, full JSON contains status, expiry, question definitions, and null answers:

<!-- example:retrieval-response -->

```json
{
  "status": "awaiting_answer",
  "expires_at": "2026-10-25T12:01:00Z",
  "questions": [
    {
      "id": "q1",
      "name": "Drink?",
      "type": "radio",
      "answers": [
        "beer",
        "water"
      ]
    },
    {
      "id": "q2",
      "name": "Sides?",
      "type": "checkbox",
      "answers": [
        "rice",
        "salad"
      ]
    }
  ],
  "answers": null
}
```

After submission, `status` is `answered` and `answers` maps every question ID to its selected option array. Reads are
non-destructive. For polling only the result:

<!-- example:answer-only -->

```shell
curl -sS "$URL?answer_only=1"
```

<!-- example:answer-only-response -->

```json
{
  "status": "answered",
  "answers": {
    "q1": [
      "beer"
    ],
    "q2": [
      "rice",
      "salad"
    ]
  }
}
```

An HTML-oriented `Accept` receives the answering page. The same URL accepts the recipient's normal form POST; a second
submission returns `409` and cannot overwrite the first answer.

### Stream the answer with SSE

Native `EventSource` uses the same secret URL with `Accept: text/event-stream`. The stream starts with `retry: 5000` and
an immediate `status` event, emits named `heartbeat` events while waiting, and closes after terminal `answer` or
`expired`. Close the client after either terminal event so it does not automatically reconnect.

<!-- example:sse-client -->

```javascript
const source = new EventSource(URL);

source.addEventListener("status", (event) => {
  console.log("questionnaire", JSON.parse(event.data));
});
source.addEventListener("heartbeat", (event) => {
  console.log("alive", JSON.parse(event.data).time);
});
source.addEventListener("answer", (event) => {
  console.log("answers", JSON.parse(event.data).answers);
  source.close();
});
source.addEventListener("expired", () => source.close());
```

The terminal answer data has the same status/answers shape as answer-only polling:

<!-- example:sse-answer -->

```json
{
  "status": "answered",
  "answers": {
    "q1": [
      "beer"
    ],
    "q2": [
      "rice",
      "salad"
    ]
  }
}
```

An interrupted connection can reconnect to the same URL after the suggested delay; Klaro sends current state, not
historical heartbeat replay. For a command-line stream, use `curl -N -H "Accept: text/event-stream" "$URL"`.

### Confirm reception explicitly

After learning the answer, permanently delete it with a POST. A GET with `confirmed=1` never mutates state.

<!-- example:confirm -->

```shell
curl -sS -X POST "$URL?confirmed=1"
```

<!-- example:confirmation-response -->

```json
{
  "status": "confirmed"
}
```

Confirmation before submission returns `409`; confirmation after deletion and all unknown, expired, or deleted URLs
return the same generic `404`.

## Capability URL and answering rules

The secret URL is the only credential for answering, JSON retrieval, confirmation, and SSE. Anyone who possesses it can
perform those operations; it is not tied to a Pushover account or device. Share it only through the intended
notification, use HTTPS, and consider browser history, screenshots, notifications, and proxy logs when assessing
exposure. Klaro serves assets same-origin and sends `Referrer-Policy: no-referrer`, but cannot remove a URL already
disclosed by a client or intermediary.

Each questionnaire accepts **exactly one valid submission**, even when a Pushover group or several devices receive the
same link. The first valid submission wins atomically; later submissions return `409` and cannot overwrite it. Invalid
submissions return `422` and leave answering open. After success, browser views are read-only. Retrieval is
non-destructive; only explicit POST confirmation deletes an answered questionnaire before its normal expiry.

## Configuration

Klaro uses [uv](https://docs.astral.sh/uv/) and a TOML configuration file. Select the file with the `KLARO_CONFIG`
environment variable. Startup fails when required values are missing or unsafe.

| Field                         | Required | Default          | Meaning                                                                                        |
|-------------------------------|----------|------------------|------------------------------------------------------------------------------------------------|
| `pushover.app_token`          | yes      | none             | Secret 30-character Pushover application token.                                                |
| `pushover.sound`              | no       | `pushover`       | Pushover notification sound.                                                                   |
| `pushover.priority`           | no       | `0`              | Non-emergency priority from `-2` through `1`.                                                  |
| `klaro.data_dir`              | yes      | none             | Writable questionnaire storage directory.                                                      |
| `klaro.public_address`        | yes      | none             | Absolute public HTTP(S) base URL used in secret links.                                         |
| `klaro.listen`                | no       | `127.0.0.1:3344` | Gunicorn listen address.                                                                       |
| `klaro.lifetime_seconds`      | no       | `86400`          | Total questionnaire lifetime from creation.                                                    |
| `klaro.sse_heartbeat_seconds` | no       | `15`             | Delay between observable SSE heartbeat events.                                                 |
| `klaro.questioners`           | no       | omitted          | Exact, case-sensitive questioner allowlist. Omission allows all valid labels; `[]` denies all. |
| `klaro.trusted_proxies`       | no       | `[]`             | Proxy IPs or CIDR ranges allowed to supply the client address.                                 |

Complete example (replace the example application token):

```toml
[pushover]
app_token = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
sound = "pushover"
priority = 0

[klaro]
data_dir = "/var/lib/klaro/data"
public_address = "https://klaro.example.com"
listen = "127.0.0.1:3344"
lifetime_seconds = 86400
sse_heartbeat_seconds = 15
# questioners = ["Your dinner mate"]
trusted_proxies = []
```

`data_dir` is created with owner-only permissions when absent. `public_address` must not contain a query or fragment and
must leave enough room for the complete secret URL within Pushover's 512-character supplementary-URL limit.

### Reverse proxies

By default, abuse controls use the direct peer IP and ignore forwarding headers. Add only the immediate proxy's IP or
CIDR range to `klaro.trusted_proxies` to honor its `X-Forwarded-For` header. Configure that proxy to **overwrite**
incoming forwarding headers with a sanitized end-client address; for example, a single Nginx proxy can use
`proxy_set_header X-Forwarded-For $remote_addr;`. Do not append untrusted client-supplied values with
`$proxy_add_x_forwarded_for`. Forwarding headers from every untrusted peer are ignored.

## Abuse controls and trust model

`X-Questioner` is an unauthenticated display and filtering label, not proof of identity. Klaro does not require
questioner accounts or API tokens. If `klaro.questioners` is omitted, every syntactically valid label is allowed. If
configured, the complete label must match an entry exactly, including case and whitespace. An explicitly empty
`questioners = []` denies every creation request.

Creation uses **5 creation attempts per IP per 60-second fixed window**. The first attempt starts the window. Every
`POST /` attempt counts, including invalid, forbidden, upstream-failed, rate-limited, and backoff-blocked requests.
Attempts six and later return `429` without extending the window. `Retry-After` is the ceiling of the remaining seconds;
for example, a limited attempt with 17 seconds remaining returns `Retry-After: 17`. Answering, retrieval, static assets,
and confirmation do not consume this quota.

Only Pushover's structured recipient-key rejection increases recipient backoff. The backoff delays in seconds are
`60, 120, 240, 480, 960, 1920, 3600`; subsequent rejections remain capped at 3600 seconds (60 minutes). Blocked attempts
do not change the delay or deadline. Pushover acceptance resets the schedule, while quota, application-token,
malformed-response, server, timeout, and connection failures leave it unchanged. If rate limiting and backoff both
apply, Klaro returns one `429` with the longer delay.

These controls are worker-local and reset on restart. Run **exactly one Klaro instance with exactly one gevent worker**.
Multiple workers, multiple instances, and horizontal coordination are unsupported; their rate and backoff state would
not be shared.

## Operations

### Install and start

For a source checkout, install the locked development environment and run the checks:

<!-- operation:development -->

```shell
uv sync --frozen
uv run playwright install chromium
uv run pytest
```

For production, choose a service-owned runtime root. The defaults below are suitable for an unprivileged local
installation; a system service can instead use paths such as `/var/lib/klaro` and `/etc/klaro/klaro.toml`.

<!-- operation:environment -->

```shell
export KLARO_ROOT="${KLARO_ROOT:-$PWD/.klaro-runtime}"
export KLARO_DATA="$KLARO_ROOT/data"
export KLARO_CONFIG="$KLARO_ROOT/klaro.toml"
export KLARO_BACKUP="$KLARO_ROOT/backup"
export KLARO_RESTORE="$KLARO_ROOT/restored-data"
export KLARO_VENV="$KLARO_ROOT/venv"
export KLARO_WHEEL="$PWD/dist/klaro-0.1.0-py3-none-any.whl"
```

Create the initial paths, then write the TOML configuration shown above to `$KLARO_CONFIG`:

<!-- operation:filesystem-setup -->

```shell
install -d -m 700 "$KLARO_ROOT"
install -d -m 700 "$KLARO_DATA"
install -m 600 /dev/null "$KLARO_CONFIG"
```

Build and install the wheel, then start Klaro through its launcher:

<!-- operation:production -->

```shell
uv build
uv venv "$KLARO_VENV"
uv pip install --python "$KLARO_VENV/bin/python" "$KLARO_WHEEL"
"$KLARO_VENV/bin/klaro" --config "$KLARO_CONFIG"
```

From a source checkout, the equivalent command is `uv run klaro --config ./klaro.toml` (or use `-c`). The launcher
validates the TOML, sets `KLARO_CONFIG` to its absolute path, and starts Gunicorn with `python:klaro.gunicorn_conf` and
`klaro.app:create_app()`. Klaro's `--config` accepts TOML; Gunicorn's own `--config` remains a separate Python-settings
option. The packaged configuration uses `klaro.listen`, one gevent worker, and at most 1,000 worker connections. Do not
override the worker count or run old and new instances simultaneously. Start cleanup only through this worker hook, not
in a second scheduler process.

The service user must own `$KLARO_DATA`; use mode `700` for data directories and `600` for the configuration and
questionnaire JSON files. Klaro creates new data directories as `700` and new records as `600`, but does not change an
existing directory's owner or mode. Protect the Pushover application token in the configuration and treat questionnaire
filenames as bearer secrets. `/var/lib/klaro/data` and `/etc/klaro/klaro.toml` are conventional production locations,
not paths hard-coded into the application.

### Reverse proxy and SSE operation

Terminate TLS at the proxy, forward to the configured `klaro.listen` address, and use the proxy sanitization rules
above. Disable response buffering and caching for SSE. For Nginx with the default 15-second heartbeat, a suitable
location block is:

```nginx
location / {
    proxy_pass http://127.0.0.1:3344;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 75s;
}
```

Keep proxy and idle-connection timeouts comfortably longer than `klaro.sse_heartbeat_seconds`; if that interval changes,
adjust the proxy too. Klaro also sends `X-Accel-Buffering: no`. Native `EventSource` receives a five-second reconnection
hint. After a process restart it can reconnect to current persisted state, but Klaro does not replay old heartbeats or
events. Active and answered records survive restart; unpublished pending records are removed during recovery. Unknown,
expired, or deleted URLs still return `404`.

### Clocks, expiry, and upstream failure behavior

Synchronize the host clock with a reliable time service and monitor clock drift. Expiry timestamps use UTC wall-clock
time; fixed-window rate limiting and backoff use monotonic time. Do not manually move the clock to extend a
questionnaire.

`klaro.lifetime_seconds` is the total lifetime from creation, including Pushover publication latency and any time spent
answered but unconfirmed. The default is 86,400 seconds. The worker-owned cleanup scheduler checks every 30 seconds,
while retrieval, confirmation, and SSE waits also check expiry lazily. Heartbeats and client connections never extend
the deadline.

Pushover HTTP 200 with `status: 1` means accepted and queued, not delivered to a device. Klaro makes one outbound
attempt with a 3.05-second connect timeout and 15-second read timeout and never retries automatically. On timeout,
connection failure, malformed response, or server error, it deletes pending data and returns `502`; a notification may
nevertheless have been queued, leaving its recipient with a dead link that returns generic `404`. A structured recipient
rejection returns `422`, deletes pending data, and starts recipient backoff. Later retrieval is non-destructive, and
only explicit POST confirmation deletes an answered record before expiry.

### Backup and rollback

Questionnaires are normally short-lived, so backups may be unnecessary. If required, stop the sole service instance
before copying so no write is in progress, and make a filesystem-consistent copy. Atomic record replacement prevents
partial JSON files but does not make a live multi-file backup a point-in-time snapshot. Encrypt and restrict backups:
token filenames and answer contents are sensitive even though recipient and application keys are not stored.

Back up the configured data directory, not a hard-coded path:

<!-- operation:backup -->

```shell
install -d -m 700 "$KLARO_BACKUP"
cp -a "$KLARO_DATA/." "$KLARO_BACKUP/"
```

For data rollback, keep the service stopped and restore into a new empty directory rather than merging into live data:

<!-- operation:rollback -->

```shell
install -d -m 700 "$KLARO_RESTORE"
cp -a "$KLARO_BACKUP/." "$KLARO_RESTORE/"
```

Verify ownership and mode `700`, set `klaro.data_dir` to `$KLARO_RESTORE`, and start only the restored instance. For
application rollback, stop the service, set `$KLARO_WHEEL` to the previously built wheel, and repeat the
virtual-environment installation and Gunicorn command above. Keep the matching pre-upgrade data snapshot; this MVP has
no database migration or distributed rollback coordination.
