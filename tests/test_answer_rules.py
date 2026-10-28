"""Exact answer-validation messages and stored-answer invariants (found by mutation testing)."""

from __future__ import annotations

import pytest

from klaro.answers import (
    AnswerValidationError,
    SubmittedAnswer,
    is_consistent_answer,
    validate_answers,
)
from klaro.limits import MAX_TEXT_CHARACTERS
from klaro.models import Question, QuestionKind

RADIO = Question(id="q1", name="One", kind=QuestionKind.RADIO, answers=("a", "b"))
CHECKBOX = Question(
    id="q2",
    name="Many",
    kind=QuestionKind.CHECKBOX,
    answers=("x", "y"),
    allow_other=True,
    allow_comments=True,
)

# A kind outside QuestionKind, as a corrupted stored record could contain.
UNKNOWN_KIND = Question(
    id="q3",
    name="Odd",
    kind="free",  # type: ignore[arg-type]
    answers=("a", "b"),
)


def field_errors(submission: dict[str, list[str]]) -> dict[str, list[str]]:
    with pytest.raises(AnswerValidationError) as caught:
        validate_answers((RADIO, CHECKBOX), submission)
    return caught.value.fields


@pytest.mark.parametrize(
    ("submission", "field", "message"),
    [
        ({"q1": ["1", "2"], "q2": ["1"]}, "q1", "Select exactly one answer."),
        ({"q1": ["1"], "q2": ["1", "1"]}, "q2", "Select each option at most once."),
        ({"q1": ["3"], "q2": ["1"]}, "q1", "Select only the offered options."),
        ({"q1": ["other"], "q2": ["1"]}, "q1", "Select only the offered options."),
        (
            {"q1": ["1"], "q2": ["1"], "q9": ["1"]},
            "q9",
            "This question is not part of the questionnaire.",
        ),
        (
            {"q1": ["1"], "q2": ["1"], "q2-comment": ["x" * (MAX_TEXT_CHARACTERS + 1)]},
            "q2-comment",
            f"Must contain at most {MAX_TEXT_CHARACTERS} characters.",
        ),
        ({"q1": ["1"], "q2": ["other"]}, "q2-other", "Describe your other answer."),
    ],
)
def test_each_rejection_reports_its_exact_field_message(
    submission: dict[str, list[str]], field: str, message: str
) -> None:
    assert field_errors(submission)[field] == [message]


def test_other_is_rejected_where_it_is_not_offered_even_alone() -> None:
    errors = field_errors({"q1": ["other"], "q2": ["1"]})

    assert set(errors) == {"q1"}


@pytest.mark.parametrize(
    ("question", "answer", "consistent"),
    [
        (RADIO, SubmittedAnswer(("a",)), True),
        (RADIO, SubmittedAnswer(("c",)), False),
        (RADIO, SubmittedAnswer((1,)), False),  # type: ignore[arg-type]
        (RADIO, SubmittedAnswer(("a", "b")), False),
        (RADIO, SubmittedAnswer(()), False),
        (RADIO, SubmittedAnswer((), other="mine"), False),
        (RADIO, SubmittedAnswer(("a",), comment="note"), False),
        (CHECKBOX, SubmittedAnswer(("x", "x")), False),
        (CHECKBOX, SubmittedAnswer(()), False),
        (CHECKBOX, SubmittedAnswer((), other="mine"), True),
        (CHECKBOX, SubmittedAnswer(("x",), other="mine", comment="note"), True),
        (CHECKBOX, SubmittedAnswer(("x",), other=" padded "), False),
        (CHECKBOX, SubmittedAnswer(("x",), other=""), False),
        (CHECKBOX, SubmittedAnswer(("x",), comment="c" * (MAX_TEXT_CHARACTERS + 1)), False),
        (UNKNOWN_KIND, SubmittedAnswer(("a",)), False),
    ],
)
def test_stored_answer_consistency(
    question: Question, answer: SubmittedAnswer, consistent: bool
) -> None:
    assert is_consistent_answer(question, answer) is consistent
