# Spec Delta

## MODIFIED Requirements

### Requirement: Questionnaire schema and limits

A questionnaire SHALL contain 1-20 questions with exact case-sensitive unique names. Each SHALL have a nonempty name up to 500 characters, radio or checkbox type, and 2-50 distinct nonempty options up to 200 characters. Optional allow_other and allow_comments SHALL be booleans defaulting to false. Optional recommendations SHALL be an array of unique integer 1-based offered-option indices, defaulting to empty.

#### Scenario: Valid question types
- **WHEN** questions have supported types, unique names and valid limits, flags and recommendation indices
- **THEN** creation accepts the questionnaire

#### Scenario: Unsupported fields or values
- **WHEN** input contains a free-text question type, confirm_reception, unknown fields, duplicate options, invalid counts, over-limit strings, nonboolean flags or invalid recommendations
- **THEN** creation returns `400 invalid_request` with field-specific errors and no notification or retained record

#### Scenario: Oversized request body
- **WHEN** a creation body exceeds 65,536 bytes before decoding
- **THEN** creation returns `413` without parsing it or calling Pushover

#### Scenario: Duplicate question name
- **WHEN** a question repeats an earlier exact name
- **THEN** creation returns `400 invalid_request` with `fields["questions.<index>.name"]` equal to `["Question names must be unique."]` for the later zero-based index without notification or retained data

#### Scenario: Names differing in case or whitespace
- **WHEN** names differ only in case or surrounding whitespace
- **THEN** they remain distinct and are preserved without normalization

### Requirement: Full questionnaire retrieval

Full JSON SHALL return exactly expires_at, answered_at and ordered questions, each containing name, type, offered answers, allow_other, allow_comments, answered, other, comment and recommendations. Recommendations SHALL contain sorted configured indices both before and after answering. IDs, status, created_at and questioner SHALL be omitted. HTML and SSE negotiation SHALL retain their existing behavior.

#### Scenario: Poll before answering
- **WHEN** full JSON is retrieved before submission
- **THEN** answered_at, answered, other and comment are null, flags reflect the definition, and recommendations contains sorted configured indices or an empty array

#### Scenario: Read after answering
- **WHEN** full JSON is retrieved after submission
- **THEN** it contains the unchanged recommendation metadata, original expiry, persisted timestamp and answers without mutating data or retention

### Requirement: Answer-only polling

Answer-only GET SHALL return exactly answered_at and ordered questions containing exactly name, answered, other, comment and recommendations. Recommendation indices SHALL match full JSON both before and after submission. All answer-only values SHALL match SSE answer data. Polling SHALL remain repeatable and non-destructive.

#### Scenario: Answer is not ready
- **WHEN** polling precedes submission
- **THEN** answered_at, answered, other and comment are null and recommendations contains the sorted configured indices

#### Scenario: Answer is ready
- **WHEN** polling follows submission
- **THEN** it returns the persisted timestamp, selections, normalized text and unchanged recommendation indices without modifying retention

## ADDED Requirements

### Requirement: Dedicated recommendation metadata

Recommendations SHALL be accepted only through the recommendations key, with strictly integer indices excluding booleans, unique and within the offered option range. Invalid values SHALL return `400 invalid_request` at `questions.<index>.recommendations`. Stored and returned indices SHALL be sorted ascending and survive restart. Option strings SHALL remain unchanged; prefixes SHALL NOT imply recommendations.

#### Scenario: Multiple recommendations
- **WHEN** recommendations is `[4, 1]` for four options
- **THEN** stored, full JSON, polling and SSE metadata is `[1, 4]`, including after restart

#### Scenario: Invalid recommendation list
- **WHEN** recommendations is null, a scalar, contains duplicates, booleans, strings, floats, zero, negative or out-of-range indices
- **THEN** creation returns `400 invalid_request` at the recommendations field without notification or retained data

#### Scenario: Literal leading asterisks
- **WHEN** an option starts with `*` or a backslash and no recommendation list is supplied
- **THEN** it has no recommendation and the source string is retained exactly, including in answered values

#### Scenario: Other cannot be recommended
- **WHEN** recommendations refers to `other` or to an index beyond the offered options on an allow_other question
- **THEN** creation rejects the list even though Other is available as an answer

### Requirement: Recommendations are guidance without selection

Recommended choices SHALL display accessible Recommended tabs with petrol styling, while selected state remains orange. No recommendation SHALL preselect an input, satisfy required selection, or influence progress. When recommendations exist, the form SHALL state `Recommendations come from {questioner}. Nothing is preselected.` No per-question recommendation count or star icon SHALL be shown.

#### Scenario: Initial recommendation presentation
- **WHEN** a radio or checkbox question has recommendations
- **THEN** Recommended is included in each recommended choice's accessible label, all choices start unchecked and progress is zero

#### Scenario: Recipient chooses freely
- **WHEN** a recipient selects a recommended choice, another choice, or permitted Other
- **THEN** validation and storage follow the same selection rules, and choosing a recommendation shows orange selection while retaining its petrol tab

#### Scenario: Recommendations remain usable without JavaScript
- **WHEN** a recipient uses a 320px viewport or keyboard with scripts disabled
- **THEN** recommendation tabs and 44px choice targets remain usable without page overflow and nothing becomes preselected

### Requirement: Read-only recommendation presentation

Read-only views SHALL mark chosen recommended options with a Recommended badge. Recommended options that were not selected SHALL appear separately with a Recommended tab and `not chosen` text. These displays SHALL NOT modify the answered arrays or imply the recipient selected unchosen recommendations.

#### Scenario: Selected and unselected recommendations
- **WHEN** the recipient selects one of two recommended choices
- **THEN** the selected answer has its badge and the other appears in a separate not-chosen block, while JSON contains only the actual selected answers

#### Scenario: Other instead of a recommendation
- **WHEN** the recipient chooses only Other
- **THEN** read-only text shows Other as the answer and all recommended offered choices separately as not chosen
