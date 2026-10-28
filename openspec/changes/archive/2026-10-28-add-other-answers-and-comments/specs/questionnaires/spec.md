# Spec Delta

## MODIFIED Requirements

### Requirement: Questionnaire schema and limits

A questionnaire SHALL contain 1-20 questions with exact case-sensitive unique names. Each question SHALL have a nonempty name of at most 500 characters, type radio or checkbox, and 2-50 distinct nonempty answer options of at most 200 characters. Optional `allow_other` and `allow_comments` SHALL be booleans defaulting to false.

#### Scenario: Valid question types
- **WHEN** all questions have supported types, unique names and values within limits
- **THEN** schema validation accepts the questionnaire, including either opt-in flag

#### Scenario: Unsupported fields or values
- **WHEN** input contains a free-text question type, confirm_reception, unknown fields, duplicate options, invalid counts, over-limit strings or nonboolean opt-in flags
- **THEN** creation returns `400 invalid_request` with field-specific errors and no notification or retained record

#### Scenario: Oversized request body
- **WHEN** a creation body exceeds 65,536 bytes before decoding
- **THEN** the service returns `413` without parsing it or calling Pushover

#### Scenario: Duplicate question name
- **WHEN** a question repeats an earlier exact name
- **THEN** creation returns `400 invalid_request` with `fields["questions.<index>.name"]` equal to `["Question names must be unique."]` for the later zero-based index without notification or retained data

#### Scenario: Names differing in case or whitespace
- **WHEN** names differ only in case or surrounding whitespace
- **THEN** they remain distinct and are preserved without normalization

### Requirement: Complete answer submission

Every question SHALL require a selection. Offered choices SHALL use canonical ASCII decimal 1-based indices mapped to exact source strings. Enabled Other SHALL use `other`: radio accepts exactly one choice; checkbox accepts one or more distinct choices including Other. Invalid submissions SHALL return `422` field errors and leave answering open. Valid submissions SHALL atomically store offered choices, Other, comments and one UTC `answered_at`.

#### Scenario: Incomplete or forged answers
- **WHEN** submission omits a selection, repeats a choice, sends multiple radio choices, unknown fields, a disabled Other choice or invalid indices
- **THEN** the service returns `422` and stores nothing

#### Scenario: Valid submission
- **WHEN** all choices and enabled text fields are valid
- **THEN** exact offered strings in submitted order, normalized text and answered_at are stored together and answering closes

#### Scenario: Noncanonical indices
- **WHEN** an offered choice index is zero, padded, signed, fractional, non-ASCII or out of range
- **THEN** it is rejected with `422` rather than coerced

#### Scenario: Text resembling an index
- **WHEN** options are `["2", "1"]` and the submitted offered index is `1`
- **THEN** the selected source value is `"2"`

#### Scenario: Validation preserves valid selections
- **WHEN** an HTML or HTMX submission has an invalid field
- **THEN** its `422` page or fragment preserves valid selections and submitted text, and reopens comments containing text or errors

### Requirement: Full questionnaire retrieval

JSON retrieval SHALL return exactly `expires_at`, `answered_at`, and ordered `questions`. Each question SHALL contain `name`, `type`, offered `answers`, `allow_other`, `allow_comments`, selected `answered`, `other`, `comment`, and `recommendations`. IDs, status, created_at and questioner SHALL be omitted. HTML requests SHALL receive HTML; SSE requests SHALL use the stream contract.

#### Scenario: Poll before answering
- **WHEN** full JSON is retrieved before submission
- **THEN** answered_at, answered, other and comment are null, both flags reflect the definition, and recommendations is empty

#### Scenario: Read after answering
- **WHEN** full JSON is retrieved after submission
- **THEN** it contains original expiry, persisted answered_at, exact offered selections and normalized Other/comment values without changing retention or data

### Requirement: Answer-only polling

Answer-only GET SHALL return exactly `answered_at` and ordered `questions`, each containing exactly `name`, `answered`, `other`, `comment`, and `recommendations`. These values SHALL match full retrieval and SSE answer data, omitting opt-in flags and definitions. Polling SHALL be repeatable and non-destructive.

#### Scenario: Answer is not ready
- **WHEN** answer-only polling precedes submission
- **THEN** answered_at, answered, other and comment are null and recommendations is empty

#### Scenario: Answer is ready
- **WHEN** answer-only polling follows submission
- **THEN** it returns the persisted timestamp, offered selections and normalized text, using null for unused text and an empty answered array for Other-only selections

### Requirement: Persistent questionnaire state

Published definitions, choices, Other, comments and answered_at SHALL survive normal process restart. Restart SHALL NOT change timestamps or expiry. Pending interrupted notifications SHALL NOT become published. Exactly one complete winning submission SHALL persist atomically.

#### Scenario: Restart after answering
- **WHEN** an answered questionnaire with Other and comments is reloaded after restart
- **THEN** its flags, exact choices, texts, timestamp and expiry remain available for JSON, HTML, SSE and confirmation

#### Scenario: First submission fixes the answer timestamp
- **WHEN** valid submissions with different text race or a later submission is attempted
- **THEN** only the winning choices, texts and timestamp persist together and the loser receives `409`

## ADDED Requirements

### Requirement: Optional text answer semantics

Enabled Other and comment fields SHALL accept at most one submitted value each. Other SHALL trim surrounding whitespace and require nonempty text when selected; unselected Other text SHALL be ignored. Comments SHALL be optional, trimmed, and null when blank. Both normalized values SHALL be limited to 2,000 Unicode code points. Disabled text fields SHALL be rejected even when empty.

#### Scenario: Radio Other selection
- **WHEN** a radio question permits Other and only Other with valid text is selected
- **THEN** answered is `[]` and other contains trimmed text

#### Scenario: Checkbox Other selection
- **WHEN** an enabled checkbox Other is selected alone or alongside offered choices
- **THEN** the selection is complete and answered contains only offered choices while other contains the separate text

#### Scenario: Other needs a description
- **WHEN** Other is selected with missing or whitespace-only text
- **THEN** `422` includes `Describe your other answer.` at `<qid>-other`

#### Scenario: Disabled and repeated text fields
- **WHEN** a disabled `<qid>-other` or `<qid>-comment` field is submitted, or an enabled field has multiple submitted values
- **THEN** submission returns `422` with field errors rather than accepting ambiguous text

#### Scenario: Text field boundaries
- **WHEN** enabled normalized Other or comment text has 2,000 or 2,001 Unicode code points within the body cap
- **THEN** 2,000 is accepted and 2,001 returns `422` at that text field

#### Scenario: Comment does not answer a question
- **WHEN** a comment is submitted without any valid selection
- **THEN** submission returns `422` for the missing selection and preserves the comment

#### Scenario: Plain text rendering
- **WHEN** Other or comments contain HTML, Markdown, ampersands or line breaks
- **THEN** they are displayed as escaped plain text with line breaks preserved and returned as text, without executing markup

### Requirement: Mobile text entry controls

Enabled Other SHALL appear as the last option labeled Other with an associated textarea. Comments SHALL use native details/summary with an accessible icon control. Controls SHALL work by keyboard and without JavaScript at 320px with no page overflow, with visible focus and 44px targets. Read-only views SHALL identify Other and Your comment separately.

#### Scenario: Other and comment correction without scripts
- **WHEN** a no-JavaScript recipient opens comments, chooses Other, submits invalid text and corrects it
- **THEN** labels, errors, selections and entered text remain usable and the valid submission reaches the read-only view

#### Scenario: Text entry with HTMX
- **WHEN** a mobile recipient corrects a text field error through HTMX
- **THEN** the fragment keeps entered values and accessible field-error associations and a subsequent valid submission displays both text types correctly

### Requirement: Answer request body limits

Answer POST bodies SHALL have a 524,288-byte limit before decoding; creation and confirmation SHALL retain the 65,536-byte limit. Exceeding a limit SHALL return `413` without storing answers. The byte limit SHALL apply independently of character limits, including encoding overhead. HTMX answer errors SHALL leave the existing form and all entered values in place and show an accessible size error.

#### Scenario: Separate creation and answer caps
- **WHEN** a valid answer body is larger than 65,536 but no larger than 524,288 bytes
- **THEN** it reaches field validation, while a creation body of the same size returns `413`

#### Scenario: Aggregate Unicode body exceeds cap
- **WHEN** a URL-encoded answer exceeds 524,288 bytes even though each text field is within 2,000 characters
- **THEN** it returns `413` without accepting a partial answer; HTMX displays the size error without replacing or clearing the form

#### Scenario: Full-page oversized submission
- **WHEN** a non-HTMX answer exceeds the cap
- **THEN** it receives an understandable `413` response and the questionnaire remains answerable without parsing and echoing the oversized body
