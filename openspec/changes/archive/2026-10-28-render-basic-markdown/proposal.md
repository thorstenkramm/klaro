# Proposal

## Why

Technical questions and options need readable emphasis and code examples. A small server-rendered Markdown subset can improve readability while retaining source strings and the existing same-origin CSP.

## What Changes

- Render emphasis, strong emphasis and inline code in names; render those plus paragraphs, line breaks, fenced and indented code in options.
- **BREAKING:** require option content to begin with a nonempty paragraph; reject code-first options with `400 invalid_request`. Use the first paragraph as the clickable head and render remaining content underneath outside the label.
- Increase each option's source limit from 200 to 2,000 characters; keep names at 500 and creation bodies at 65,536 bytes.
- Display unsupported syntax, including raw HTML, links, images, headings, lists, tables and quotes, as literal text. Names remain inline-only, including literal fenced syntax.
- Keep API/storage values as original source; Other and comments remain escaped plain text. Recommendations use their dedicated key only.
- Send the first question to Pushover as plain text derived from supported inline formatting.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `questionnaires`: option limits, restricted Markdown presentation, option-head validation and plain-text notification content.

## Impact

Adds a focused server-side rendering module and `markdown-it-py` dependency, updating lockfile and bundled third-party notices. Changes models, templates, CSS and Pushover formatting, plus security/browser/API/packaging tests and documentation. Apply and synchronize after recommendations, preserving schema 4 source-string storage. No browser renderer, external assets or migration.
