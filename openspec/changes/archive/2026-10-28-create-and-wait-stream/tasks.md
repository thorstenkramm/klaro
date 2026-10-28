# Tasks

## 1. Creation negotiation and redirect

- [x] 1.1 Implement explicit preferred-SSE negotiation on creation and the empty relative 303 after publication; verify JSON/YAML 201 defaults, weighted Accept, wildcard/tie/q=0 cases, zero body and exact Location in creation API tests, and document the opt-in contract in README.
- [x] 1.2 Cover failure and security behavior for SSE creation: verify validation, allowlist, body limit, rate-limit/backoff and Pushover failures retain JSON errors/Retry-After without redirects; verify hostile Host and differing public_address cannot change Location origin, and tokens/credentials remain redacted.

## 2. Single-command journeys and coverage

- [x] 2.1 Add the executable README curl command with URL write-out and explicit confirmation guidance; verify a real subprocess follows creation POST with a bodyless GET, receives retry/status/answer or expiry and exits, with no automatic confirmation or second notification.
- [x] 2.2 Add a deterministic answer-before-redirect journey and an error journey; verify immediate answer has no waiting status, effective-URL output permits confirmation, and --fail-with-body returns nonzero with the JSON error. Document reconnect limitations and avoid forced POST redirect options.
- [x] 2.3 Extend scenario coverage to an ordered explicit set of implemented deltas with ADDED/MODIFIED support; add this change's executable references and verify current coverage plus simulated synchronization/archive while leaving pending-only changes, main specs and historical artifacts untouched.

## 3. Integrated verification

- [x] 3.1 Run the full pytest suite, Ruff lint/format checks and strict validation of create-and-wait-stream; verify production launcher/open-stream concurrency, clean wheel installation and redacted logs still pass.

## Workflow follow-up

- Review and synchronize/archive unify-response-format before synchronizing/archiving this change.
- Continue with add-other-answers-and-comments, then add-answer-recommendations, then render-basic-markdown.
