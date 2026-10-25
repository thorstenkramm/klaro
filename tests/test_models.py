from __future__ import annotations

import pytest

from klaro.models import SchemaValidationError, validate_questionnaire


def question(kind: str = "radio", answers: list[str] | None = None) -> dict:
    return {
        "name": "What would you like?",
        "type": kind,
        "answers": answers if answers is not None else ["beer", "water"],
    }


def payload(questions: list[dict] | None = None) -> dict:
    return {"questions": questions if questions is not None else [question()]}


def test_valid_questions_receive_sequential_ids_and_preserve_options() -> None:
    raw = payload(
        [
            question(answers=[" beer ", "Beer"]),
            question("checkbox", ["rice", "salad", "rice "]),
        ]
    )

    questions = validate_questionnaire(raw)

    assert [item.id for item in questions] == ["q1", "q2"]
    assert questions[0].answers == (" beer ", "Beer")
    assert questions[1].answers == ("rice", "salad", "rice ")
    assert questions[0].as_dict() == {
        "id": "q1",
        "name": "What would you like?",
        "type": "radio",
        "answers": [" beer ", "Beer"],
    }


@pytest.mark.parametrize("count", [1, 20])
def test_question_count_boundaries(count: int) -> None:
    assert len(validate_questionnaire(payload([question()] * count))) == count


@pytest.mark.parametrize("count", [0, 21])
def test_invalid_question_counts(count: int) -> None:
    with pytest.raises(SchemaValidationError, match="between 1 and 20"):
        validate_questionnaire(payload([question()] * count))


@pytest.mark.parametrize("length", [1, 500])
def test_question_name_length_boundaries(length: int) -> None:
    item = question()
    item["name"] = "ä" * length
    assert validate_questionnaire(payload([item]))[0].name == "ä" * length


@pytest.mark.parametrize("name", ["", " ", "x" * 501, 42, None])
def test_invalid_question_names(name: object) -> None:
    item = question()
    item["name"] = name
    with pytest.raises(SchemaValidationError, match="name"):
        validate_questionnaire(payload([item]))


@pytest.mark.parametrize("count", [2, 50])
def test_option_count_boundaries(count: int) -> None:
    options = [f"option-{index}" for index in range(count)]
    assert len(validate_questionnaire(payload([question(answers=options)]))[0].answers) == count


@pytest.mark.parametrize("count", [0, 1, 51])
def test_invalid_option_counts(count: int) -> None:
    with pytest.raises(SchemaValidationError, match="between 2 and 50"):
        validate_questionnaire(payload([question(answers=[str(i) for i in range(count)])]))


@pytest.mark.parametrize("length", [1, 200])
def test_option_length_boundaries(length: int) -> None:
    option = "x" * length
    assert (
        validate_questionnaire(payload([question(answers=[option, "other"])]))[0].answers[0]
        == option
    )


@pytest.mark.parametrize("option", ["", " ", "x" * 201, 1, None, ["nested"]])
def test_invalid_options(option: object) -> None:
    with pytest.raises(SchemaValidationError):
        validate_questionnaire(payload([question(answers=[option, "other"])]))


def test_exact_duplicate_options_are_rejected() -> None:
    with pytest.raises(SchemaValidationError, match="distinct"):
        validate_questionnaire(payload([question(answers=["same", "same"])]))


@pytest.mark.parametrize("kind", ["text", "free-text", "Radio", "", None, 1])
def test_unsupported_question_types(kind: object) -> None:
    with pytest.raises(SchemaValidationError, match="radio or checkbox"):
        validate_questionnaire(payload([question(kind=kind)]))


@pytest.mark.parametrize("field", ["confirm_reception", "required", "unknown"])
def test_unknown_question_fields(field: str) -> None:
    item = question()
    item[field] = True
    with pytest.raises(SchemaValidationError, match="not supported"):
        validate_questionnaire(payload([item]))


def test_unknown_top_level_field() -> None:
    raw = payload()
    raw["surprise"] = True
    with pytest.raises(SchemaValidationError, match="surprise"):
        validate_questionnaire(raw)


@pytest.mark.parametrize("field", ["name", "type", "answers"])
def test_missing_question_fields(field: str) -> None:
    item = question()
    del item[field]
    with pytest.raises(SchemaValidationError, match="required"):
        validate_questionnaire(payload([item]))


@pytest.mark.parametrize("raw", [None, [], "questions", 1])
def test_root_must_be_object(raw: object) -> None:
    with pytest.raises(SchemaValidationError, match="object"):
        validate_questionnaire(raw)


def test_questions_must_be_array() -> None:
    with pytest.raises(SchemaValidationError, match="array"):
        validate_questionnaire({"questions": {}})


def test_answers_must_be_array() -> None:
    item = question()
    item["answers"] = "beer,water"
    with pytest.raises(SchemaValidationError, match="array"):
        validate_questionnaire(payload([item]))


def test_validation_contains_machine_readable_field_path() -> None:
    with pytest.raises(SchemaValidationError) as caught:
        validate_questionnaire(payload([question(answers=["only"])]))
    assert caught.value.fields == {
        "questions.0.answers": ["Must contain between 2 and 50 answer options."]
    }
