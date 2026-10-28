# Design

## Context

See proposal.md. Unified projections already emit recommendations but always as an empty array. The preceding Other/comments change introduces a container/head option structure and schema 3. This plan targets that state, not the earlier handover's prefix-stripping convention. The user's dedicated-key decision is authoritative.

## Goals / Non-Goals

**Goals:** Make recommendation metadata durable and visually accessible without coupling it to response selection or altering source strings.

**Non-Goals:** Defaults/preselection, automatic selection, recommending Other, asterisk parsing or recommendation counts.

## Decisions

1. Add `recommendations: tuple[int, ...] = ()` to `Question`. Accept a list only; validate `type(index) is int` to exclude booleans, validate range/uniqueness, then sort. All failures use `questions.<zero-based-index>.recommendations`. Do not silently deduplicate or coerce numeric strings/floats. Tests cover JSON and YAML types and no creation side effects.
2. Store the normalized indices with the question definition and emit them through the shared question-answer projection, regardless of submission state. This makes polling and SSE equal while avoiding multiple serializers. Upgrade to schema 4 so old readers cannot silently discard recommendation metadata. Include flags and rich answers from schema 3; no migration.
3. Keep offered strings byte-for-byte as decoded source text; duplicate option validation remains exact and precedes any future Markdown display. `*wine` and `\\*wine` do not change recommendations or stored answers. Recommendations affect neither answer cardinality nor progress.
4. Use the handover's Recommended tab design: petrol border/tab, orange selected border, darker petrol tab when selected, no star. Include badge text in the input's accessible name, preserving a single associated label and 44px target. Add the questioner-source footer only when any question has recommendations, with normal escaping. All styling stays in `klaro.css`; no JS is required.
5. Read-only answers identify selected indices by matching exact source strings (options remain unique), show a badge for selected recommendations, and list unchosen recommended options separately in definition order. Other is never matched against offered text, even when its contents equal an option. Tests assert these sections do not pollute the public answered arrays.
6. Extend scenario coverage only when this change is implemented. Run exact full/poll/SSE shape tests with unsorted input indices, restart tests, and mobile/keyboard/no-JavaScript tests that explicitly assert zero checked inputs and zero initial progress.

## Risks / Trade-offs

- Python bool is a subclass of int → use strict integer checks and test true/false in JSON and YAML.
- Badge text can make existing label-text assertions fail → update expectations to distinguish option text from accessible recommendation metadata.
- Long labels and tabs can overflow → 320px coverage with long strings and multiple recommended choices; no per-question count.
- Source text equal to Other → use the structured Other field rather than treating it as an offered selection.

## Migration Plan

Apply after Other/comments; deploy schema 4 using a new empty owned directory, with no migration or automatic deletion. Roll back to the prior build with its own compatible empty directory. Synchronize specs in sequence so recommendations replaces empty placeholders without losing Other/comment requirements. Markdown keeps this record schema and only changes rendering later.
