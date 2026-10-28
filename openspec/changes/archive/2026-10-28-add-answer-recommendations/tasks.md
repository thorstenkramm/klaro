# Tasks

## 1. Recommendation definition and persistence

- [x] 1.1 Accept strict unique integer 1-based recommendations and normalize them ascending; verify empty/default lists, booleans, strings, floats, duplicates, ranges and Other rejection for JSON/YAML with exact field paths and no creation side effects. Update README examples to use only the dedicated key and test literal asterisk/backslash source preservation.
- [x] 1.2 Persist recommendation indices in schema 4 definitions and read them through the common response projection; update storage/version documentation and verify exact full/poll/SSE values before/after answers, restart retention, unsupported-version handling and fresh-directory rollback procedure.

## 2. Recommendation presentation

- [x] 2.1 Add accessible petrol Recommended tabs, selected-state styles and the escaped questioner footer using local CSS/templates; verify radio and checkbox inputs remain unchecked, initial progress stays zero, required selection still applies, no star/count is rendered and labels/44px targets remain accessible. Document the guidance-only behavior.
- [x] 2.2 Add read-only badges for selected recommendations and separate not-chosen blocks; verify selecting recommended/nonrecommended/Other answers, multiple recommendations, exact source text and no extra values in answered arrays in template and API tests.
- [x] 2.3 Exercise recommendations in mobile/keyboard/no-JavaScript and HTMX correction flows, including long labels and Other/comments; verify 320px layout, visible focus, no preselection after initial load, preserved recipient choices after 422 and no CSP errors in Chrome.

## 3. Integrated verification

- [x] 3.1 Add recommendation scenarios and executable references to the implemented-delta coverage list; verify effective specs and simulated sync/archive, then run end-to-end create-and-wait/polling journeys with restart, unchanged metadata, stable timestamp and explicit confirmation.
- [x] 3.2 Run full pytest, Ruff lint/format checks and strict validation of add-answer-recommendations; verify production concurrency, redaction and clean wheel startup remain passing.

## Workflow follow-up

- Apply after add-other-answers-and-comments; review and synchronize/archive after all predecessors.
- Continue with render-basic-markdown without introducing prefix-based recommendations.
