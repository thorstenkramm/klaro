"""Validate complete form submissions against the offered options."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from klaro.models import Question


class AnswerValidationError(ValueError):
    def __init__(self, fields: dict[str, list[str]]) -> None:
        super().__init__("The answers are incomplete or invalid")
        self.fields = fields


def validate_answers(
    questions: Sequence[Question], submission: Mapping[str, list[str]]
) -> dict[str, tuple[str, ...]]:
    fields: dict[str, list[str]] = {}
    known = {question.id for question in questions}
    for question_id in submission.keys() - known:
        fields[question_id] = ["This question is not part of the questionnaire."]

    answers: dict[str, tuple[str, ...]] = {}
    for question in questions:
        values = submission.get(question.id, [])
        if not values:
            fields[question.id] = [
                "Select an answer." if question.kind == "radio" else "Select at least one answer."
            ]
            continue
        if question.kind == "radio" and len(values) != 1:
            fields[question.id] = ["Select exactly one answer."]
            continue
        if len(set(values)) != len(values):
            fields[question.id] = ["Select each option at most once."]
            continue
        if any(value not in question.answers for value in values):
            fields[question.id] = ["Select only the offered options."]
            continue
        answers[question.id] = tuple(values)

    if fields:
        raise AnswerValidationError(fields)
    return answers
