from __future__ import annotations

import pytest

from klaro.answers import AnswerValidationError, SubmittedAnswer, validate_answers
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

    answers = validate_answers(questions, {"q1": ["1"], "q2": ["2", "1"]})

    assert answers == {
        "q1": SubmittedAnswer((" beer ",)),
        "q2": SubmittedAnswer(("salad", "Äpfel")),
    }


@pytest.mark.parametrize(
    ("submission", "invalid_fields"),
    [
        ({}, ["q1", "q2"]),
        ({"q1": ["1"]}, ["q2"]),
        ({"q2": ["1"]}, ["q1"]),
        ({"q1": ["1", "2"], "q2": ["1"]}, ["q1"]),
        ({"q1": [], "q2": []}, ["q1", "q2"]),
        ({"q1": ["wine"], "q2": ["1"]}, ["q1"]),
        ({"q1": ["1"], "q2": ["chips"]}, ["q2"]),
        ({"q1": ["1"], "q2": ["1", "1"]}, ["q2"]),
        ({"q1": ["1"], "q2": ["1"], "q99": ["forged"]}, ["q99"]),
        ({"q1": [""], "q2": ["1"]}, ["q1"]),
    ],
)
def test_incomplete_multiple_forged_and_unknown_answers_have_field_errors(
    submission: dict[str, list[str]], invalid_fields: list[str]
) -> None:
    with pytest.raises(AnswerValidationError) as caught:
        validate_answers(QUESTIONS, submission)

    assert list(caught.value.fields) == invalid_fields


# Arabic-Indic and fullwidth digits are deliberate: only ASCII digits are canonical.
NON_ASCII_DIGITS = ["١", "１"]  # noqa: RUF001


@pytest.mark.parametrize(
    "value", ["0", "3", "01", "+1", "-1", "1.0", " 1", "1 ", *NON_ASCII_DIGITS, "beer"]
)
def test_noncanonical_or_out_of_range_index_is_rejected(value):
    with pytest.raises(AnswerValidationError) as caught:
        validate_answers(QUESTIONS, {"q1": [value], "q2": ["1"]})
    assert set(caught.value.fields) == {"q1"}


def test_numeric_option_text_is_not_an_index():
    question = Question(id="q1", name="Numbers?", kind="radio", answers=("2", "1"))
    assert validate_answers([question], {"q1": ["1"]}) == {"q1": SubmittedAnswer(("2",))}


def text_question(kind: str = "radio") -> Question:
    return Question(
        id="q1",
        name="Custom?",
        kind=kind,
        answers=("one", "two"),
        allow_other=True,
        allow_comments=True,
    )


def test_radio_other_is_separate_from_offered_answers() -> None:
    result = validate_answers(
        [text_question()],
        {"q1": ["other"], "q1-other": ["  custom\nanswer  "], "q1-comment": ["  note  "]},
    )
    assert result == {"q1": SubmittedAnswer((), "custom\nanswer", "note")}


@pytest.mark.parametrize("values", [["other"], ["2", "other", "1"]])
def test_checkbox_other_can_be_alone_or_with_offered_options(values: list[str]) -> None:
    result = validate_answers([text_question("checkbox")], {"q1": values, "q1-other": [" custom "]})
    assert result["q1"].other == "custom"
    assert result["q1"].answered == tuple(
        {"1": "one", "2": "two"}[value] for value in values if value != "other"
    )


@pytest.mark.parametrize("text", [None, "", "   "])
def test_selected_other_requires_nonempty_trimmed_text(text: str | None) -> None:
    submission = {"q1": ["other"], "q1-comment": ["note"]}
    if text is not None:
        submission["q1-other"] = [text]
    with pytest.raises(AnswerValidationError) as caught:
        validate_answers([text_question()], submission)
    assert caught.value.fields == {"q1-other": ["Describe your other answer."]}


def test_unselected_other_text_is_ignored_and_blank_comment_is_null() -> None:
    result = validate_answers(
        [text_question()],
        {"q1": ["1"], "q1-other": [" ignored "], "q1-comment": [" \n "]},
    )
    assert result == {"q1": SubmittedAnswer(("one",))}


@pytest.mark.parametrize("field", ["q1-other", "q1-comment"])
def test_text_fields_are_rejected_when_disabled_even_if_empty(field: str) -> None:
    with pytest.raises(AnswerValidationError) as caught:
        validate_answers(QUESTIONS[:1], {"q1": ["1"], field: [""]})
    assert set(caught.value.fields) == {field}


@pytest.mark.parametrize("field", ["q1-other", "q1-comment"])
def test_text_fields_reject_repeated_values(field: str) -> None:
    with pytest.raises(AnswerValidationError) as caught:
        validate_answers([text_question()], {"q1": ["1"], field: ["one", "two"]})
    assert caught.value.fields == {field: ["Submit at most one value."]}


@pytest.mark.parametrize(("length", "valid"), [(2_000, True), (2_001, False)])
def test_other_and_comment_use_unicode_code_point_limits(length: int, valid: bool) -> None:
    text = "😀" * length
    submission = {"q1": ["other"], "q1-other": [text], "q1-comment": [text]}
    if valid:
        result = validate_answers([text_question()], submission)
        assert result["q1"].other == text
        assert result["q1"].comment == text
    else:
        with pytest.raises(AnswerValidationError) as caught:
            validate_answers([text_question()], submission)
        assert set(caught.value.fields) == {"q1-other", "q1-comment"}


def test_comment_does_not_replace_required_selection() -> None:
    with pytest.raises(AnswerValidationError) as caught:
        validate_answers([text_question()], {"q1-comment": ["context"]})
    assert caught.value.fields == {"q1": ["Select an answer."]}
