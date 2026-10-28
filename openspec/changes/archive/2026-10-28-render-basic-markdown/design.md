# Design

## Context

See proposal.md. Current names/options are escaped strings; Pushover embeds the first question's source verbatim. Index-valued form submissions and separate public projections already preserve source. Earlier changes provide option containers, Other/comments and recommendation badges; all remain server-rendered with local CSS/JS and strict CSP. `pyproject.toml` currently has no Markdown library.

## Goals / Non-Goals

**Goals:** One bounded rendering policy for active and read-only views, safe source fidelity and valid label markup; a plain-text variant for Pushover.

**Non-Goals:** Full CommonMark, rich links/images, syntax highlighting, browser rendering, Markdown in respondent text, changing storage representations or interpreting recommendation prefixes.

## Decisions

1. Add a small `markdown.py` module using `markdown-it-py` with a zero preset and an explicit rule allowlist for paragraphs/text, emphasis, backticks, breaks and option-only code/fences. Current library docs confirm configurable rules and token inspection. Pin an appropriate supported major range, update `uv.lock` and the packaged notices. Prefer this established tokenizer to handwritten Markdown parsing; do not use the permissive default preset or plugins.
2. Provide separate name-inline, option-block and plain-name-text entry points backed by the same policy. Rendering emits only a fixed tag allowlist: strong, em, code, p, br and pre as appropriate. Escape every text/code token; suppress fence-info-generated classes and all user-supplied attributes. Wrap only renderer-produced markup as safe for Jinja. Links, images, raw HTML, headings, lists, tables and quotes remain disabled and literal. Test nested hostile syntax rather than relying solely on html=False or CSP.
3. Names must preserve unsupported fenced constructs literally, including triple-backtick delimiters. Plain renderInline alone could consume them as code spans; protect detected block-like fence runs as text tokens before inline processing, without activating block rendering. Plain-text notification conversion walks the safe inline tokens, retaining literal unsupported syntax and removing only supported formatting delimiters. Do not strip syntax with a broad regex that corrupts code, escapes or literal text.
4. Parse each option into block tokens once per rendering/validation operation. After blank lines the first meaningful block must be a nonempty paragraph; otherwise fail at the zero-based option field. Extract its inline tokens for the clickable head; render the remaining paragraphs/code as descriptive siblings outside the label. Leading inline code in a paragraph is valid; a leading block of code is not. Blank-line detection and fence interruption follow the parser, shared between schema validation and rendering.
5. Change only the option source limit to 2,000 code points; leave the creation byte cap, 500-character name limit, name uniqueness and option distinctness based on exact source. Rendering must never normalize stored API strings, including trailing newlines. Selecting via indices maps back to source strings, not generated HTML. Validation of unsupported syntax is literal-display behavior, not an unsupported-syntax error; only limits and text-first block structure cause rejection.
6. Use existing option-head containers. Descriptive content gets stable internal IDs referenced by aria-describedby; pre blocks get tabindex=0 and an accessible code description. CSS constrains min-width, uses internal overflow-x:auto, dark code backgrounds, inline-code chips and inherited emphasis color. No pre or p element sits inside a label. Render the same option structure in answers and not-chosen recommendations, without controls in read-only views.
7. Other, comments and questioner remain autoescaped plain text. Only names/options call the renderer. Pushover converts supported inline name formatting to plain text before existing truncation and never enables Pushover HTML formatting.
8. Security tests inspect generated DOM for forbidden tags/attributes/URLs and network requests, including raw HTML, entities, escaped delimiters, javascript URLs, image syntax and hostile fence info. Browser tests assert content selection in code does not choose the option, keyboard code scrolling, no page overflow at 320px, no-JavaScript usability and no CSP violations. Clean wheel tests exercise renderer import and template output.

## Risks / Trade-offs

- Merely disabling parser rules may still allow nested formatting inside unsupported syntax → test literal cases explicitly, preserving unsupported construct delimiters and preventing active elements; token handling stays in one module.
- Code blocks can escape labels or overflow cards → token-based head/body split plus semantic DOM and mobile browser checks.
- Some old code-first strings become invalid on new creation → document text-first requirement and `400` field path. No production data exists; no migration is required.
- Rendering cost grows with options → source and creation byte caps bound work; avoid parsing the same option repeatedly in one template and never run code/highlighters.

## Migration Plan

Apply after recommendations. Schema 4 continues to store source strings; deploy updated dependencies and packaged assets together. Rollback restores plain-text display and shorter creation limits, without rewriting records. Run clean-wheel startup/rendering checks and update Markdown examples with valid YAML block scalars. Synchronize this delta last, preserving preceding flags, recommendations and response contracts.
