# Design

## Context

See proposal.md for motivation. `app.py` creates and publishes before returning 201; `_wants_sse()` already negotiates GET streams. `sse.py` sends retry then either a waiting status (with configured absolute URL) or an immediate terminal answer. The main specs still predate the completed `unify-response-format` delta; use that implemented contract as the baseline, and synchronize it first when archiving.

## Goals / Non-Goals

**Goals:** Reuse the existing GET stream and abuse/publication pipeline with a minimal creation-response branch; prove behavior with real curl, including races.

**Non-Goals:** Streaming from the POST handler, storing recipient headers, replaying events, changing answer payloads or automatically confirming receipt.

## Decisions

1. After `record_acceptance`, return an explicit empty `Response(status=303)` with `Location` built from the validated generated record token as `/<token>`. Avoid Flask's HTML redirect helper and avoid the configured absolute address for this header. Reusing the GET handler is simpler than introducing a second stream entry point; 307/308 would preserve POST and be incorrect here.
2. Prefer SSE only when the Accept field explicitly includes `text/event-stream` at positive quality and its effective quality is strictly higher than HTML and JSON. Ties and wildcards retain 201. Share negotiation logic with GET where compatible and test existing GET semantics against regressions.
3. Keep the publication transaction, rate limit, backoff, pending cleanup and generic errors ahead of this branch. No redirect on any failure. The response still passes existing no-store, referrer and logging filters.
4. README's command uses `curl -NsS -L --fail-with-body --write-out '%{stderr}\nURL: %{url_effective}\n'` with `--data-binary`, not `-X POST` or `--post303`. Waiting clients discover the configured absolute URL in status; curl's effective URL provides a same-origin usable URL when the answer precedes GET. The write-out is client output on stderr, not a server payload or log, and is not evidence of successful creation on error. On transport failure, captured redirect headers (`--dump-header` to a local file) can aid reconnect; no new server event is needed.
5. Execute the documented command against a local server with mocked Pushover, capture method/path and stdout/stderr, and coordinate submission with receipt of status. Force the fast-answer race in a separate deterministic test by committing the answer after publication but before returning the 303. Verify GET receives no request body and credentials never appear in application/Gunicorn logs.
6. Replace the current single `CHANGE_NAME` coverage overlay with an explicit ordered list of implemented deltas. Add this change only when its tests exist; do not treat the other newly planned deltas as implemented coverage. Support ADDED and MODIFIED requirement sections, reject unsupported operations explicitly, and test in-memory sync/archive equivalence without editing main or historical specs.

## Risks / Trade-offs

- Custom curl headers follow redirects → relative same-origin Location, tests with hostile Host and mismatched public_address, no automatic external redirect.
- Answer before redirect → effective URL output avoids adding a synthetic waiting event or secret fields to answer JSON.
- Curl does not reconnect SSE automatically → explain retry and explicit confirmation in docs.
- Pending changes share specification blocks → apply and synchronize in the stated order, retaining all prior scenarios.

## Migration Plan

No data migration. Deploy after the unified-response change. Ordinary clients keep 201. Rollback restores ordinary creation for all clients; opt-in clients must then use the existing two-step workflow. Review and archive unified responses before archiving this change; archive is a separate workflow.
