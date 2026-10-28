# Design

## Context

See proposal.md. The review fixes for C1, C2, H3, H4 and M5 changed no specified behaviour (memory bounds, rendering
cost, tooling, single-source limits, module structure). This change records only the observable behaviour from H1, H2,
M1, M2, M3 and M6, applied after `render-basic-markdown`.

## Goals / Non-Goals

**Goals:** Keep every client-input failure inside the JSON error contract; make abuse controls effective against
address rotation without new identity; never serve or indefinitely retain unreadable data; give HTMX users reliable
focus, announcements, and single submissions.

**Non-Goals:** Accounts or per-user credentials, sub-path hosting, a JSON variant of answer submission, record
migration, or quarantine directories.

## Decisions

1. **Nesting:** map `RecursionError` from the JSON and YAML parsers to `400 invalid_request` and suppress the parser
   traceback. A depth pre-scan was rejected as duplicate parsing.
2. **Unexpected errors:** an `InternalServerError` handler returns the JSON contract unless `text/html` is explicitly
   listed and preferred (browsers), because `*/*` API clients such as curl must not receive HTML.
3. **Path prefixes:** reject `public_address` paths at startup instead of supporting `SCRIPT_NAME`; redirects, form
   actions, and assets are root-relative and the README documents root deployment only.
4. **Client grouping:** key abuse state by IPv4 address or IPv6 /64 network, and IPv4-mapped IPv6 as IPv4. A /64 is the
   usual allocation to one subscriber; shared /64s therefore share an allowance (documented trade-off).
5. **Backoff expiry:** forget a client's backoff level once `blocked_until + maximum_delay` has passed. Escalation stays
   intact for repeated rejections within an hour of a block, and rotating clients cannot accumulate state.
6. **Unreadable records:** decoding failures behave like absent records on every route (generic `404`). They are logged
   once per file without the token and deleted once `lifetime_seconds` have passed since the file's last modification.
   No readable record can be older, so the deletion guarantee holds without quarantine copies of sensitive data.
7. **Answer feedback:** a persistent `role="status"` region outside the swap target announces non-alert results;
   `htmx:afterSwap` focuses the error summary (`role="alert"`) or the "Answer stored" heading. `hx-sync="this:drop"`
   and `hx-disabled-elt` prevent duplicate requests. Radio groups expose `role="radiogroup"` with `aria-required`;
   error lists keep list semantics inside an alert container.

## Risks / Trade-offs

- Shared IPv6 /64 or IPv4 NAT clients share limits → documented; operators can still allow-list questioner labels.
- Deleting unreadable files after their lifetime removes evidence → one warning per file is logged first.
- Startup now fails for path-prefixed addresses → documented in the README and proposal impact.

## Migration Plan

No data migration; schema 4 is unchanged. Deployments with a path in `public_address` must move Klaro to the root of its
own host name before upgrading.
