"""Validate complete form submissions against the offered options and text opt-ins."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from klaro.limits import MAX_TEXT_CHARACTERS
from klaro.models import Question, QuestionKind


@dataclass(frozen=True, slots=True)
class SubmittedAnswer:
    answered: tuple[str, ...]
    other: str | None = None
    comment: str | None = None


def _is_valid_text(value: str | None, *, enabled: bool) -> bool:
    if value is None:
        return True
    return (
        enabled
        and isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and len(value) <= MAX_TEXT_CHARACTERS
    )


def is_consistent_answer(question: Question, answer: SubmittedAnswer) -> bool:
    """Return whether an answer satisfies every invariant a valid submission produces."""
    selected = answer.answered
    if (
        any(not isinstance(value, str) or value not in question.answers for value in selected)
        or len(set(selected)) != len(selected)
        or not _is_valid_text(answer.other, enabled=question.allow_other)
        or not _is_valid_text(answer.comment, enabled=question.allow_comments)
    ):
        return False
    if question.kind == QuestionKind.RADIO:
        return (len(selected) == 1 and answer.other is None) or (
            not selected and answer.other is not None
        )
    if question.kind == QuestionKind.CHECKBOX:
        return bool(selected) or answer.other is not None
    return False


class AnswerValidationError(ValueError):
    def __init__(self, fields: dict[str, list[str]]) -> None:
        super().__init__("The answers are incomplete or invalid")
        self.fields = fields


def _text_value(
    submission: Mapping[str, list[str]],
    field: str,
    errors: dict[str, list[str]],
    *,
    maximum: int = MAX_TEXT_CHARACTERS,
) -> str | None:
    values = submission.get(field, [])
    if len(values) > 1:
        errors[field] = ["Submit at most one value."]
        return None
    value = values[0].strip() if values else ""
    if len(value) > maximum:
        errors[field] = [f"Must contain at most {maximum} characters."]
        return None
    return value or None


def _known_fields(questions: Sequence[Question]) -> set[str]:
    known = {question.id for question in questions}
    for question in questions:
        if question.allow_other:
            known.add(f"{question.id}-other")
        if question.allow_comments:
            known.add(f"{question.id}-comment")
    return known


def _selection_error(
    question: Question, values: list[str], options: Mapping[str, str]
) -> str | None:
    """Return the field error for the submitted option indices, if any."""
    error = None
    if not values:
        error = (
            "Select an answer."
            if question.kind == QuestionKind.RADIO
            else "Select at least one answer."
        )
    elif question.kind == QuestionKind.RADIO and len(values) != 1:
        error = "Select exactly one answer."
    elif len(set(values)) != len(values):
        error = "Select each option at most once."
    # An unknown or not-offered index is the most specific problem, so it takes precedence.
    if any(value != "other" and value not in options for value in values) or (
        "other" in values and not question.allow_other
    ):
        error = "Select only the offered options."
    return error


def _other_text(
    question: Question,
    values: list[str],
    submission: Mapping[str, list[str]],
    errors: dict[str, list[str]],
) -> str | None:
    if not question.allow_other:
        return None
    other_field = f"{question.id}-other"
    other = _text_value(submission, other_field, errors)
    if "other" not in values:
        return None
    if other is None and other_field not in errors:
        errors[other_field] = ["Describe your other answer."]
    return other


def _validate_question(
    question: Question, submission: Mapping[str, list[str]], errors: dict[str, list[str]]
) -> SubmittedAnswer:
    values = submission.get(question.id, [])
    options = {str(index): option for index, option in enumerate(question.answers, 1)}
    selection_error = _selection_error(question, values, options)
    if selection_error is not None:
        errors[question.id] = [selection_error]
    other = _other_text(question, values, submission, errors)
    comment = None
    if question.allow_comments:
        comment = _text_value(submission, f"{question.id}-comment", errors)
    return SubmittedAnswer(
        answered=tuple(options[value] for value in values if value in options),
        other=other,
        comment=comment,
    )


def validate_answers(
    questions: Sequence[Question], submission: Mapping[str, list[str]]
) -> dict[str, SubmittedAnswer]:
    fields: dict[str, list[str]] = {}
    for field in submission.keys() - _known_fields(questions):
        fields[field] = ["This question is not part of the questionnaire."]
    answers = {
        question.id: _validate_question(question, submission, fields) for question in questions
    }
    if fields:
        raise AnswerValidationError(fields)
    return answers
