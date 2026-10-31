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

Question names must be unique by exact, case-sensitive comparison; whitespace is preserved. A duplicate
returns `400 invalid_request` with `questions.<index>.name: ["Question names must be unique."]`
(zero-based index), before any notification is sent or questionnaire is retained.

Each question has 2–50 offered options. A questionnaire has 1–20 questions; every question is required, and only `radio`
and `checkbox` are supported. Internal form field IDs are assigned as `q1`, `q2`, and so on in input order;
these IDs are not part of the public JSON representation. Optional `allow_other` and `allow_comments` flags default
to `false` and must be JSON/YAML booleans, not strings or numbers:

```yaml
questions:
  - name: Drink?
    type: radio
    answers: [beer, water]
    allow_other: true
    allow_comments: true
    recommendations: [2]
```

`recommendations` is an optional array of unique, strictly integer 1-based offered-option indices. It defaults to `[]`
and is normalized into ascending order. It is guidance only: recommendations never preselect an answer or satisfy a
required selection, and Other cannot be recommended. Asterisks and backslashes in option strings have no special
meaning and are preserved literally. The form states that recommendations come from the questioner and nothing is
preselected.

When enabled, Other is the last form option and submits the reserved choice `other` with text in `<qid>-other`.
Radio Other replaces an offered selection; checkbox Other can be selected alone or with offered choices. Selected
Other text is required. Comments use `<qid>-comment` and never replace a selection. Both fields are trimmed, limited
to 2,000 Unicode code points, and returned separately from offered answers. Blank comments become `null`; unselected
Other text is ignored. Disabled fields and repeated text values are rejected with `422`. In the browser, Other reveals
its labeled textarea when selected; comments use a native details/summary control. Optional JavaScript counts Unicode
code points, while all controls and correction workflows work without scripts.

Answer submissions have a separate **524,288-byte aggregate body cap**, including URL encoding or multipart overhead;
creation and confirmation remain limited to 65,536 bytes. This byte cap is independent of each field's 2,000-code-point
limit, so a combination of individually valid Unicode fields can still exceed it and receive `413`. HTMX retains the
current selections and text so they can be shortened and retried. A full-page `413` explains the limit; use browser
Back to return, without relying on the browser to retain its form cache.

### Markdown in questions and offered options

Question names support only **strong emphasis**, *emphasis*, and `inline code`. Offered options additionally support
paragraphs, line breaks, and fenced or indented code blocks. Each option is limited to 2,000 Unicode code points and
**must begin with a nonempty text paragraph**: that paragraph becomes its clickable label, and later paragraphs/code
appear as descriptive content. A fenced or indented code-first option returns `400` at its source field, even after
leading blank lines. Leading inline code within a paragraph is valid.

Raw HTML, links, images, headings, lists, tables, and quotes are displayed as literal text, never as active markup.
Fenced or indented block-like syntax in names also remains literal. Other text, comments, and the questioner label are
always plain text. Storage, full JSON, polling, and SSE retain exact source strings, including Markdown and trailing
newlines; form submissions still use option indices and responses never contain generated HTML.

<!-- example:markdown-yaml -->

````yaml
questions:
  - name: How do you want me to clean up `/your-folder`?
    type: radio
    recommendations: [2]
    answers:
      - |
        Delete recursively
        ```
        cd /your-folder
        rm -rf
        pkill my-process
        ```
      - |
        Delete with a *loop*
        ```
        cd /your-folder
        for file in *.png; do
          rm "$file"
        done
        pkill my-process
        ```
````

### Create and wait in one invocation

Set `Accept: text/event-stream` to opt into a creation redirect. It must be explicitly preferred over HTML and JSON;
wildcards, equal priorities and `q=0` retain the ordinary `201` response. After Pushover accepts publication, Klaro
returns an empty `303 See Other` with a same-origin relative `Location: /<token>` header. Use `--location` to follow
it as GET; never force the redirect to remain a POST. Creation failures remain JSON errors without redirects.

<!-- example:create-and-wait -->

```shell
curl -NsS -L --fail-with-body https://klaro.example.com/ \
  --write-out '%{stderr}\nURL: %{url_effective}\n' \
  -H "Content-Type: application/yaml" \
  -H "Accept: text/event-stream" \
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

`--no-buffer` (`-N`) makes SSE observable immediately and `--fail-with-body` makes creation errors a nonzero exit
while retaining their JSON body. The URL write-out prints the secret URL to stderr on success; protect it like the
creation response. Normally the initial `status` event contains the configured absolute URL. If answering wins the
redirect race, the stream starts with the terminal answer instead, so use the effective URL printed by curl. The
command exits after `answer` or `expired`. Curl does not automatically reconnect an interrupted stream; reconnect
explicitly to the saved URL. Receiving an answer never confirms it: perform the explicit confirmation POST below.

### Retrieve the questionnaire or only its answers

Set `URL` to the complete secret URL returned by creation. Use `Accept`, not the request `Content-Type`, to negotiate
retrieval:

<!-- example:retrieve -->

```shell
curl -sS -H "Accept: application/json" "$URL"
```

Before submission, full JSON contains expiry, a null answer timestamp, and ordered question definitions:

<!-- example:retrieval-response -->

```json
{
  "answered_at": null,
  "expires_at": "2026-10-25T12:01:00Z",
  "questions": [
    {
      "name": "Drink?",
      "type": "radio",
      "answers": [
        "beer",
        "water"
      ],
      "allow_other": false,
      "allow_comments": false,
      "answered": null,
      "other": null,
      "comment": null,
      "recommendations": []
    },
    {
      "name": "Sides?",
      "type": "checkbox",
      "answers": [
        "rice",
        "salad"
      ],
      "allow_other": false,
      "allow_comments": false,
      "answered": null,
      "other": null,
      "comment": null,
      "recommendations": []
    }
  ]
}
```

After submission, `answered_at` is the persisted RFC 3339 UTC submission timestamp and each question's
`answered` contains its selected source strings. Names identify questions; public responses contain no IDs,
`status`, `created_at`, or `questioner`. Reads never change timestamps or retention.
Full definitions include both opt-in flags; polling and SSE omit them. `other` and `comment` contain normalized text
or `null` as described above. `recommendations` contains the sorted configured indices in full JSON, polling, and SSE
answers, before and after submission. Read-only views distinguish selected recommendations from recommended options
that were not chosen without adding them to `answered`.
For polling only the result (omitting expiry, type, offered options, and flags):

<!-- example:answer-only -->

```shell
curl -sS "$URL?answer_only=1"
```

<!-- example:answer-only-response -->

```json
{
  "answered_at": "2026-10-25T12:00:00Z",
  "questions": [
    {"name": "Drink?", "answered": ["beer"], "other": null, "comment": null, "recommendations": []},
    {"name": "Sides?", "answered": ["rice", "salad"], "other": null, "comment": null, "recommendations": []}
  ]
}
```

An HTML-oriented `Accept` receives the answering page. The same URL accepts the recipient's normal form POST; a second
submission returns `409` and cannot overwrite the first answer.

### Stream the answer with SSE

Native `EventSource` uses the same secret URL with `Accept: text/event-stream`. The stream starts with `retry: 5000` and
an immediate `status` event while awaiting an answer, emits named `heartbeat` events while waiting, and closes after terminal `answer` or
`expired`. Close the client after either terminal event so it does not automatically reconnect.

Every waiting `status` contains `answered_at: null`, the original `expires_at`, and the absolute secret `url`
returned by creation. This is an intentional URL disclosure to the holder; full JSON, polling, terminal answers,
errors, and logs do not contain it. Already-answered connections send the answer immediately instead of status.
An `expired` event contains only `expires_at`, even after cleanup has deleted the record.

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
  console.log("answers", JSON.parse(event.data).questions);
  source.close();
});
source.addEventListener("expired", () => source.close());
```

The terminal answer data is identical to answer-only polling:

<!-- example:sse-answer -->

```json
{
  "answered_at": "2026-10-25T12:00:00Z",
  "questions": [
    {"name": "Drink?", "answered": ["beer"], "other": null, "comment": null, "recommendations": []},
    {"name": "Sides?", "answered": ["rice", "salad"], "other": null, "comment": null, "recommendations": []}
  ]
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

HTML forms submit canonical 1-based option indices under internal field names such as `q1`.
For example, `q1=2` selects the second offered option; labels and stored answers remain the original
text. Zero, leading zeros, signs, whitespace, non-ASCII digits, and out-of-range indices are rejected
with `422`. Forms preserve valid selections on validation errors, with or without JavaScript.

The secret URL is the only credential for answering, JSON retrieval, confirmation, and SSE. Anyone who possesses it can
perform those operations; it is not tied to a Pushover account or device. Share it only through the intended
notification, use HTTPS, and consider browser history, screenshots, notifications, and proxy logs when assessing
exposure. Klaro serves assets same-origin and sends `Referrer-Policy: no-referrer`, but cannot remove a URL already
disclosed by a client or intermediary.

Each questionnaire accepts **exactly one valid submission**, even when a Pushover group or several devices receive the
same link. The first valid submission wins atomically; later submissions return `409` and cannot overwrite it. Invalid
submissions return `422` and leave answering open. After success, browser views are read-only. Retrieval is
non-destructive; only explicit POST confirmation deletes an answered questionnaire before its normal expiry.

Answer submission (`POST` of form fields to the secret URL) is **browser-only**: it always responds with an HTML page, or
an HTMX fragment for HTMX requests, including validation errors (`422`). Only an oversized answer form receives an HTML
"request too large" page; every other client error, every API route, and unexpected server errors use the JSON
`{"error": {...}}` contract. Clients that explicitly prefer `text/html` receive a plain HTML page for unexpected `500`
errors.

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

`data_dir` is created with owner-only permissions when absent. `public_address` must not contain a path, query, or
fragment, because Klaro serves its routes, redirects, form actions, and assets from the root of its own host name. It
must also leave enough room for the complete secret URL within Pushover's 512-character supplementary-URL limit.

Notifications identify the questioner, first question, and total question count. Supported strong/emphasis/inline-code
formatting in the first question is converted to plain text before Pushover truncation; code contents remain text and
unsupported syntax remains literal. Questioner text is never rendered as Markdown. Klaro does not enable Pushover HTML
and always preserves the complete supplementary capability URL.

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

Creation uses **5 creation attempts per client per 60-second fixed window**. A client is its IPv4 address, or the /64
network of its IPv6 address, because one IPv6 subscriber usually controls a whole /64; IPv4-mapped IPv6 addresses count
as their IPv4 address. Clients behind a shared IPv4 NAT or a shared /64 therefore share one allowance. The first
attempt starts the window. Every
`POST /` attempt counts, including invalid, forbidden, upstream-failed, rate-limited, and backoff-blocked requests.
Attempts six and later return `429` without extending the window. `Retry-After` is the ceiling of the remaining seconds;
for example, a limited attempt with 17 seconds remaining returns `Retry-After: 17`. Answering, retrieval, static assets,
and confirmation do not consume this quota.

Only Pushover's structured recipient-key rejection increases recipient backoff. The backoff delays in seconds are
`60, 120, 240, 480, 960, 1920, 3600`; subsequent rejections remain capped at 3600 seconds (60 minutes). Blocked attempts
do not change the delay or deadline. Pushover acceptance resets the schedule, while quota, application-token,
malformed-response, server, timeout, and connection failures leave it unchanged. A client that stays quiet for a further
3600 seconds after its block ends is forgotten and starts again at 60 seconds, so rotating clients cannot accumulate
backoff state. If rate limiting and backoff both
apply, Klaro returns one `429` with the longer delay.

These controls are worker-local and reset on restart. Run **exactly one Klaro instance with exactly one gevent worker**.
Multiple workers, multiple instances, and horizontal coordination are unsupported; their rate and backoff state would
not be shared.

## Limits and scale

Klaro is built for personal and small-team use: questionnaires live for hours, a handful are active at once, and a
single process serves everything. The design depends on that, so treat these as constraints rather than tuning knobs.

- **One instance, one gevent worker (`workers = 1`).** Per-questionnaire locks, the wake-up of waiting SSE streams, and
  the creation rate limit and backoff all live in that one process. With more workers, two submissions could race on
  the same file, a stream in one worker would miss an answer stored by another, and every worker would grant its own
  creation allowance. Scale up by giving the one worker more CPU, not by adding workers or instances.
- **Concurrent connections:** up to 1000 per worker (`worker_connections`), including every open SSE stream; each
  stream costs one greenlet and a few kilobytes while it waits.
- **Storage:** one small JSON file per questionnaire in `klaro.data_dir`. Each request reads one file; the cleanup job
  reads every file every 30 seconds, which stays cheap up to a few thousand stored questionnaires.
- **CPU:** request handling is cooperative, so long CPU work blocks everyone. Rendering is bounded and cached: even a
  deliberately pathological 64 KB questionnaire costs well under a second on its first view and about a millisecond
  afterwards.
- **Request bodies:** creation is capped at 65,536 bytes and answers at 524,288 bytes; question and option counts and
  text lengths are capped as described in the API sections.

## Operations

### Install and start

For a source checkout, install the locked development environment and run the same gates as CI
(`.github/workflows/ci.yml`). Coverage below the configured branch-coverage floor fails the test run, and
`.jscpd.json` defines the duplication threshold:

<!-- operation:development -->

```shell
uv sync --frozen
uv run playwright install chromium
uv run ruff check src tests tools
uv run ruff format --check src tests tools
uv run flake8
uv run mypy
uv run pytest --cov
npx --yes jscpd@5.4.2
npm ci
npm run lint:js
trivy fs --config trivy.yaml .
```

Node.js is only needed for these checks (duplication and ESLint); Klaro itself has no JavaScript build step. Trivy
scans both lockfiles, all files for secrets, and configuration; CI additionally uploads a report with every severity to
GitHub code scanning and repeats all checks weekly. CI also installs the built wheel with its runtime dependencies and
fails on forbidden, restricted, or unclassified licences (`trivy-license.yaml`), and lints the workflows with
actionlint and zizmor. Dependabot (`.github/dependabot.yml`) proposes grouped weekly updates for the Python and Node
lockfiles and the SHA-pinned actions.

`uvx pre-commit install` enables the fast subset (Ruff, flake8, and strict mypy) before every commit.

### Cut a release

Set `KLARO_VERSION` to the desired version, then create and push the release tag:

<!-- operation:release-tag -->

```shell
git tag -a "v$KLARO_VERSION" -m "Klaro $KLARO_VERSION"
git push origin "v$KLARO_VERSION"
```

GitHub Actions derives the package version from the tag, runs the checks, and publishes one deployment archive.

### Install a release

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) system-wide at `/usr/local/bin/uv` first.
Run these initial installation commands as root:

<!-- operation:release-install -->

```shell
set -eu
cd "$(mktemp -d)"
useradd -s /usr/sbin/nologin -r -M -d /var/lib/klaro klaro
curl -fL -o klaro.tar.gz \
  "https://github.com/thorstenkramm/klaro/releases/download/v0.1.0/klaro-0.1.0.tar.gz"
install -d -m 0755 -o root -g root /opt/klaro
tar xzf klaro.tar.gz --no-same-owner -C /opt/klaro
install -d -m 0750 -o root -g klaro /etc/klaro
install -d -m 0700 -o klaro -g klaro /var/lib/klaro /var/lib/klaro/data
install -m 0640 -o root -g klaro /opt/klaro/klaro.example.toml /etc/klaro/klaro.toml
```

Edit `/etc/klaro/klaro.toml` to set your Pushover application token and public URL, then start Klaro:

<!-- operation:release-run -->

```shell
su -s /bin/sh -c '/opt/klaro/bin/klaro' klaro
```

The launcher automatically prepares Python 3.12 and locked runtime dependencies under `/var/lib/klaro`.
First startup needs Internet access. Application files under `/opt/klaro` remain root-owned.

### Run with systemd

Stop the manually started instance first, then enable the bundled service:

<!-- operation:systemd-service -->

```shell
ln -s /opt/klaro/klaro.service /etc/systemd/system/klaro.service
systemctl daemon-reload
systemctl enable --now klaro.service
```

Use `journalctl -u klaro` for logs and `systemctl restart klaro` after a configuration change. The service starts at
boot through `multi-user.target`. Back up or restore `/var/lib/klaro/data` only while this single service is stopped.

### Run a source checkout

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
export KLARO_VERSION="${KLARO_VERSION:-$(python3 -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')}"
export KLARO_WHEEL="$PWD/dist/klaro-$KLARO_VERSION-py3-none-any.whl"
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

#### Nginx

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
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
}
```

#### Caddy

The shipped [`deploy/caddy/Caddyfile`](deploy/caddy/Caddyfile) is a complete site example. Set `KLARO_SITE` to the
public host name and run `caddy run --config /path/to/Caddyfile`; Caddy obtains and renews its TLS certificate. With
`trusted_proxies = ["127.0.0.1/32"]` in `[klaro]`, the explicit `header_up` replaces any client-supplied forwarding
value with the direct peer address. `flush_interval -1` disables proxy buffering for SSE, and no compression is
enabled. Caddy has no proxy read timeout by default, so the 15-second heartbeat keeps long-lived streams active.

<!-- example:caddyfile -->

```caddyfile
{$KLARO_SITE:klaro.example.com} {
	reverse_proxy 127.0.0.1:3344 {
		header_up X-Forwarded-For {remote_host}
		header_up X-Forwarded-Proto {scheme}
		flush_interval -1
	}
	header Strict-Transport-Security "max-age=31536000; includeSubDomains"
}
```

Send HSTS from the TLS-terminating proxy only once HTTPS works for the whole host name. Klaro itself sends a strict
`Content-Security-Policy`, `Referrer-Policy: no-referrer`, `X-Content-Type-Options: nosniff`, a `Permissions-Policy`
that denies device and payment APIs, and `Cross-Origin-Opener-Policy` and `Cross-Origin-Resource-Policy` set to
`same-origin`; the proxy must not remove them.

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

This release uses questionnaire storage schema **4**, including per-question offered answers, Other text, comments,
recommendation indices, and a persisted `answered_at` timestamp. There is no migration from schema 1, 2, or 3. For this
format-changing deployment, stop the sole instance, configure `klaro.data_dir` to a new empty directory owned by the
service user, and start the new build. Existing directories are not automatically cleared or migrated. Update API
clients to the new response format at the same time. Normal restarts of this version preserve answers, recommendations,
and their original timestamps.

A record that cannot be read (corrupt JSON, another schema version, or content that violates the current rules) is never
served: its URL behaves exactly like an unknown one (`404`). Klaro logs one warning per such file, without its token, and
deletes it once `klaro.lifetime_seconds` have passed since its last modification, which no readable record can outlive.

For rollback across this format change, stop the service and use the previous build with its own empty compatible
data directory; do not give schema-4 records to an earlier reader. The backup/restore procedure below is for data
compatible with the selected build.

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
