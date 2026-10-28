# Tasks

## 1. Restricted rendering and schema

- [x] 1.1 Add the markdown-it-py dependency, lockfile and packaged license notice, then implement the restricted name/option/plain-text renderer; verify allowed tokens, escaped hostile HTML, literal unsupported links/images/block syntax, literal name fences, safe fence info and no user-controlled attributes with renderer/security tests. Document the exact supported subset in README.
- [x] 1.2 Enforce text-first options using the renderer's block parsing and raise the source limit to 2,000; verify 2,000/2,001 boundaries, leading blank lines, fenced/indented code-first rejection with field-specific 400 and no side effects, accepted inline-code heads, unchanged exact source/name uniqueness and the 64 KiB creation cap. Add executable valid YAML examples and document the text-first requirement.

## 2. Templates, mobile layout and notifications

- [x] 2.1 Render inline names and split option heads/descriptions in active and read-only templates, including unchosen recommendations; verify no pre/p inside labels, correct aria-describedby IDs, safe markup-only trust boundaries and escaped plain-text Other/comments/questioner using DOM tests.
- [x] 2.2 Add local inline-code/emphasis/code-block styles and keyboard-focusable code regions; verify 320px internal scrolling without page overflow, text selection not selecting an option, label activation, 44px targets, no-JavaScript flow and absence of CSP violations in browser tests and Chrome.
- [x] 2.3 Convert the first question's supported inline formatting to plain text before Pushover truncation; verify supported delimiters disappear while code/literal unsupported syntax, questioner text, total count, sound/priority and complete supplementary URL remain correct, and update notification documentation.

## 3. Source fidelity and integrated verification

- [x] 3.1 Add exact source-string API/storage/SSE tests with multiline Markdown, trailing newlines, recommendations and rich answers; verify index submissions, restart, repeated polling, identical answer payloads, stable timestamps and explicit confirmation without leaking generated HTML into JSON.
- [x] 3.2 Extend current scenario coverage with this implemented delta and executable references; verify effective specs and simulated synchronization/archive retain all prior feature scenarios and run a combined JSON/SSE plus YAML/polling journey across all feedback features.
- [x] 3.3 Run full pytest, Ruff lint/format checks and strict change validation; verify production launcher/concurrency, no external browser requests, redacted logs and clean-wheel import/rendering with the new dependency and license assets.

## Workflow follow-up

- Apply after recommendations; review and synchronize/archive after all preceding feedback changes.
- Verify main-spec scenario coverage after the final archive, retaining historical artifacts unchanged.
