# Spec Delta

## MODIFIED Requirements

### Requirement: Questionnaire schema and limits

A questionnaire SHALL contain 1-20 questions with exact case-sensitive unique names. Each SHALL have a nonempty name up to 500 characters, radio or checkbox type, and 2-50 distinct nonempty options up to 2,000 characters. Optional allow_other and allow_comments SHALL be booleans defaulting to false. Optional recommendations SHALL be unique integer 1-based offered-option indices, defaulting to empty. Each option SHALL begin with a nonempty paragraph.

#### Scenario: Valid question types
- **WHEN** questions have supported types, unique names, valid flags and recommendations, and text-first options within source limits
- **THEN** creation accepts the questionnaire

#### Scenario: Unsupported fields or values
- **WHEN** input contains a free-text question type, confirm_reception, unknown fields, duplicate source options, invalid counts, over-limit source strings, nonboolean flags or invalid recommendations
- **THEN** creation returns `400 invalid_request` with field-specific errors and no notification or retained record

#### Scenario: Oversized request body
- **WHEN** a creation body exceeds 65,536 bytes before decoding, even with individually valid option lengths
- **THEN** creation returns `413` without parsing it or calling Pushover

#### Scenario: Duplicate question name
- **WHEN** a question repeats an earlier exact source name
- **THEN** creation returns `400 invalid_request` with `fields["questions.<index>.name"]` equal to `["Question names must be unique."]` for the later zero-based index without notification or retained data

#### Scenario: Names differing in case or whitespace
- **WHEN** source names differ only in case or surrounding whitespace
- **THEN** they remain distinct and are preserved without normalization

#### Scenario: Option source length boundaries
- **WHEN** a text-first option has 2,000 or 2,001 characters within the creation body limit
- **THEN** 2,000 is accepted and 2,001 returns `400` at `questions.<question-index>.answers.<option-index>`

#### Scenario: Code-first option
- **WHEN** an option begins, after blank lines, with a fenced or indented code block and has no preceding paragraph
- **THEN** creation returns `400 invalid_request` at its zero-based option field with no notification or retained record

### Requirement: Pushover notification content

The notification SHALL identify the questioner, reference the first question and total count, and carry the secret supplementary URL. Supported inline Markdown in the first question SHALL become plain text before truncation; unsupported syntax SHALL remain literal. Configured sound and non-emergency priority SHALL apply without exposing the application token.

#### Scenario: Multiple-question notification
- **WHEN** a questionnaire has multiple questions
- **THEN** the message includes the first question in plain text and the total count rather than the entire questionnaire

#### Scenario: Pushover length limits
- **WHEN** text exceeds Pushover limits
- **THEN** display text is truncated after Markdown-to-text conversion while the complete secret URL is preserved

#### Scenario: Inline formatting in notification
- **WHEN** the first question contains emphasis and inline code
- **THEN** the message contains their text without supported formatting delimiters or generated HTML

## ADDED Requirements

### Requirement: Restricted Markdown rendering

Names SHALL support strong emphasis, emphasis and inline code only. Options SHALL additionally support paragraphs, line breaks, fenced and indented code. Raw HTML, links, images, headings, lists, tables and quotes SHALL be displayed literally without active markup or external requests. Fenced syntax in names SHALL remain literal. Source strings SHALL remain unchanged in storage, full JSON, polling and SSE.

#### Scenario: Supported inline formatting
- **WHEN** a name or option contains strong emphasis, emphasis or inline code
- **THEN** the answering and read-only views display the corresponding formatting without changing the stored or returned source

#### Scenario: Unsupported and hostile syntax
- **WHEN** content includes raw script/HTML, a Markdown image or link, heading, list, table, quote or unsafe URL
- **THEN** it remains visible literal text, creates no active element or URL-bearing attribute and makes no external request

#### Scenario: Inline-only names
- **WHEN** a name contains fenced or indented block-like syntax
- **THEN** it is rendered as literal text rather than a code block, including literal fence delimiters

#### Scenario: Plain-text answer fields
- **WHEN** Other, comments or questioner text contain Markdown or HTML syntax
- **THEN** they remain escaped plain text and are not sent through the Markdown renderer

#### Scenario: Source fidelity and recommendation independence
- **WHEN** a recommended option containing Markdown is selected by index
- **THEN** every public answer returns its original source string and recommendations remain determined only by the dedicated metadata

### Requirement: Text-first option layout

An option's first paragraph SHALL be its clickable labeled head. Remaining paragraphs and code blocks SHALL appear underneath outside the label and be associated with the control as descriptive content. Code areas SHALL be keyboard-focusable and horizontally scroll internally; the page SHALL fit a 320px viewport. The same formatted content SHALL appear in selected answers and recommended-but-not-chosen views, without requiring scripts or inline styles.

#### Scenario: Paragraph and code option
- **WHEN** an option contains a text paragraph followed by code and further paragraphs
- **THEN** the first paragraph labels its index-valued input, subsequent content appears below, and selecting text in the code does not select the option

#### Scenario: Narrow keyboard and no-JavaScript view
- **WHEN** a 320px viewport displays a long code line with JavaScript disabled
- **THEN** the page has no horizontal overflow, the code box scrolls by keyboard, and the option remains selectable through its label

#### Scenario: Answered rich option
- **WHEN** a recipient submits a formatted option
- **THEN** the read-only view retains its formatting and code and the original source remains in JSON, including after restart
