# Proposal

## Why

Questioners need to suggest choices without selecting on the recipient's behalf. Existing response placeholders are ready to carry recommendation metadata.

## What Changes

- Accept only the dedicated `recommendations` array of unique, in-range, strictly integer 1-based option indices; normalize output into ascending order and default to `[]`.
- Preserve option source strings exactly. Asterisks have no recommendation meaning; the superseded prefix/escape convention is not supported.
- Display accessible petrol Recommended tabs and distinguish them from orange selected state, with no preselection and no recommendation for Other.
- Show selected recommendations and recommended-but-not-chosen options in read-only views; identify the questioner as the source of recommendations.
- Persist indices and return them consistently in full JSON, polling and SSE before and after submission.
- **BREAKING (storage):** schema 4 records include recommendation metadata; use a fresh directory for the format-changing deployment.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `questionnaires`: recommendation schema, public metadata, persistence and answering/read-only presentation.

## Impact

Touches `models.py`, `storage.py`, templates, local CSS, API/browser/restart tests and README. No dependency additions. Apply after `add-other-answers-and-comments` in the feedback sequence and synchronize in that order. Recommendations do not affect answer validation or notification content.
