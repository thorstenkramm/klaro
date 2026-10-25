from __future__ import annotations

import pytest

from klaro.answers import AnswerValidationError, validate_answers
from klaro.models import Question

QUESTIONS = [
    Question(id="q1", name="Drink?", kind="radio", answers=("beer", "water")),
    Question(id="q2", name="Sides?", kind="checkbox", answers=("rice", "salad")),
]


def test_valid_answers_preserve_exact_strings_and_order() -> None:
    questions = [
        Question(id="q1", name="Exact?", kind="radio", answers=(" beer ", "Beer")),
        Question(id="q2", name="Unicode?", kind="checkbox", answers=("Äpfel", "salad")),
    ]

    answers = validate_answers(questions, {"q1": [" beer "], "q2": ["salad", "Äpfel"]})

    assert answers == {"q1": (" beer ",), "q2": ("salad", "Äpfel")}


@pytest.mark.parametrize(
    "submission,invalid_fields",
    [
        ({}, ["q1", "q2"]),
        ({"q1": ["beer"]}, ["q2"]),
        ({"q2": ["rice"]}, ["q1"]),
        ({"q1": ["beer", "water"], "q2": ["rice"]}, ["q1"]),
        ({"q1": [], "q2": []}, ["q1", "q2"]),
        ({"q1": ["wine"], "q2": ["rice"]}, ["q1"]),
        ({"q1": ["beer"], "q2": ["chips"]}, ["q2"]),
        ({"q1": ["beer"], "q2": ["rice", "rice"]}, ["q2"]),
        ({"q1": ["beer"], "q2": ["rice"], "q99": ["forged"]}, ["q99"]),
        ({"q1": [""], "q2": ["rice"]}, ["q1"]),
    ],
)
def test_incomplete_multiple_forged_and_unknown_answers_have_field_errors(
    submission: dict[str, list[str]], invalid_fields: list[str]
) -> None:
    with pytest.raises(AnswerValidationError) as caught:
        validate_answers(QUESTIONS, submission)

    assert list(caught.value.fields) == invalid_fields
