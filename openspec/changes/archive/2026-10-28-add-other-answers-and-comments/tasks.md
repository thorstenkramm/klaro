# Tasks

## 1. Definition and submission model

- [x] 1.1 Add strict allow_other/allow_comments booleans and defaults to question validation/serialization; update README request definitions and verify JSON/YAML acceptance, rejection of numeric/string/null flags, exact field errors and no notification/file on invalid creation.
- [x] 1.2 Introduce structured per-question submission values and validate reserved Other plus optional text; verify radio and checkbox combinations, Other-only selections, exact source ordering, ignored unselected text, trimmed/null text, disabled/repeated fields, comment-only rejection and Unicode 2,000/2,001 boundaries in answer tests; document field names and normalization.

## 2. Atomic persistence and public data

- [x] 2.1 Implement schema 3 encoding/decoding and atomic rich-answer storage with answered_at; adapt storage fixtures and verify pending/answered invariants, complete qid sets, permitted text, version rejection, concurrent winners and restart preservation. Update fresh-directory deployment/rollback documentation without migration or automatic deletion.
- [x] 2.2 Populate other/comment through the shared projection and expose flags only in full definitions; update executable README examples and expected-response helpers, and verify exact full/poll/SSE key sets, Other-only empty arrays, unused nulls, original expiry and identical stable timestamps.

## 3. Form UI and accessibility

- [x] 3.1 Refactor option containers/heads and add labeled Other textarea plus native comments details/summary; add scoped local styles following the handover and verify 44px targets, associated field errors, preserved 422 values, reopened comments and no-JavaScript correction in template/browser tests. Document optional controls in README.
- [x] 3.2 Render escaped read-only Other and Your comment blocks with line breaks and update progressive counters/progress; verify HTML/Markdown-looking respondent text remains literal, Unicode counters use code points, comments do not satisfy progress and valid Other works at 320px with keyboard and no scripts.

## 4. Request bounds and recoverable errors

- [x] 4.1 Configure the 524,288-byte answer-only request cap before parsing while retaining 65,536 for creation/confirmation; verify boundary and missing/deceptive Content-Length cases supported by the WSGI harness, URL-encoded and multipart limits, no lower accidental parser cap, no writes on rejection and accurate 413 messages. Document aggregate byte/Unicode overhead separately from character limits.
- [x] 4.2 Add accessible HTMX 413 handling without replacing the form and an understandable full-page error; verify a worst-case Unicode request exceeding the cap preserves current DOM selections/text and allows shortening/retry, with no inline scripts/styles or CSP violations, and document full-page recovery behavior.

## 5. Integrated verification

- [x] 5.1 Add this implemented delta and its test references to scenario coverage; verify effective specs and simulated sync/archive preserve predecessor scenarios, then run complete create-and-wait and polling journeys with Other/comments, restart, competing submissions, explicit confirmation and expiry.
- [x] 5.2 Test the richer UI in Chrome at 320px, checking HTMX errors, no-JavaScript fallback, keyboard, no overflow and console CSP errors; run full pytest, Ruff lint/format checks, strict change validation, production concurrency and clean-wheel checks, resolving failures before completion.

## Workflow follow-up

- Apply after create-and-wait-stream and unify-response-format; review and synchronize/archive in dependency order.
- Continue with add-answer-recommendations, preserving the rich-answer fields and body limits.
