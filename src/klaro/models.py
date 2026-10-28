"""Questionnaire API models and strict input validation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, NoReturn

from klaro.limits import (
    MAX_NAME_CHARACTERS,
    MAX_OPTION_CHARACTERS,
    MAX_OPTIONS,
    MAX_QUESTIONS,
    MIN_OPTIONS,
    MIN_QUESTIONS,
)
from klaro.markdown import is_text_first_option


class QuestionKind(StrEnum):
    RADIO = "radio"
    CHECKBOX = "checkbox"


QUESTION_FIELDS = frozenset(
    {"name", "type", "answers", "allow_other", "allow_comments", "recommendations"}
)


class SchemaValidationError(ValueError):
    """A field-aware questionnaire validation failure."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field
        self.message = message
        self.fields = {field: [message]}


@dataclass(frozen=True, slots=True)
class Question:
    id: str
    name: str
    kind: QuestionKind
    answers: tuple[str, ...]
    allow_other: bool = False
    allow_comments: bool = False
    recommendations: tuple[int, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": str(self.kind),
            "answers": list(self.answers),
            "allow_other": self.allow_other,
            "allow_comments": self.allow_comments,
            "recommendations": list(self.recommendations),
        }


def question_id(index: int) -> str:
    """Return the stable form-field ID of the zero-based question index."""
    return f"q{index + 1}"


def _fail(field: str, message: str) -> NoReturn:
    raise SchemaValidationError(field, message)


def _required(mapping: Mapping[str, Any], key: str, path: str) -> Any:
    if key not in mapping:
        _fail(f"{path}.{key}" if path else key, "This field is required.")
    return mapping[key]


def _reject_unknown(mapping: Mapping[str, Any], allowed: frozenset[str], path: str) -> None:
    for key in mapping:
        if key not in allowed:
            field = f"{path}.{key}" if path else str(key)
            _fail(field, "This field is not supported.")


def _text(value: Any, field: str, maximum: int) -> str:
    if not isinstance(value, str):
        _fail(field, "Must be a string.")
    if not value.strip():
        _fail(field, "Must contain at least one non-whitespace character.")
    if len(value) > maximum:
        _fail(field, f"Must contain at most {maximum} characters.")
    return value


def recommendations_are_valid(values: Any, option_count: int) -> bool:
    """Recommendations are unique, in-range, strictly integer 1-based option indices."""
    return (
        isinstance(values, list | tuple)
        and all(type(value) is int for value in values)
        and len(set(values)) == len(values)
        and all(1 <= value <= option_count for value in values)
    )


def _question_name(raw: dict[str, Any], path: str, seen_names: set[str]) -> str:
    name = _text(_required(raw, "name", path), f"{path}.name", MAX_NAME_CHARACTERS)
    if name in seen_names:
        _fail(f"{path}.name", "Question names must be unique.")
    seen_names.add(name)
    return name


def _question_flags(raw: dict[str, Any], path: str) -> dict[str, bool]:
    flags: dict[str, bool] = {}
    for flag in ("allow_other", "allow_comments"):
        value = raw.get(flag, False)
        if type(value) is not bool:
            _fail(f"{path}.{flag}", "Must be a boolean.")
        flags[flag] = value
    return flags


def _question_kind(raw: dict[str, Any], path: str) -> QuestionKind:
    kind_raw = _required(raw, "type", path)
    if not isinstance(kind_raw, str) or kind_raw not in set(QuestionKind):
        _fail(f"{path}.type", "Must be either radio or checkbox.")
    return QuestionKind(kind_raw)


def _question_options(raw: dict[str, Any], path: str) -> tuple[str, ...]:
    options_raw = _required(raw, "answers", path)
    if not isinstance(options_raw, list):
        _fail(f"{path}.answers", "Must be an array of answer options.")
    if not MIN_OPTIONS <= len(options_raw) <= MAX_OPTIONS:
        _fail(
            f"{path}.answers",
            f"Must contain between {MIN_OPTIONS} and {MAX_OPTIONS} answer options.",
        )
    options: list[str] = []
    for option_index, option_raw in enumerate(options_raw):
        option_path = f"{path}.answers.{option_index}"
        option = _text(option_raw, option_path, MAX_OPTION_CHARACTERS)
        if not is_text_first_option(option):
            _fail(option_path, "Must begin with a nonempty paragraph before any code block.")
        if option in options:
            _fail(option_path, "Answer options must be distinct.")
        options.append(option)
    return tuple(options)


def _question_recommendations(raw: dict[str, Any], path: str, option_count: int) -> tuple[int, ...]:
    recommendations_raw = raw.get("recommendations", [])
    if not isinstance(recommendations_raw, list):
        _fail(f"{path}.recommendations", "Must be an array of answer indices.")
    if not recommendations_are_valid(recommendations_raw, option_count):
        _fail(
            f"{path}.recommendations",
            "Must contain unique, in-range integer answer indices.",
        )
    return tuple(sorted(recommendations_raw))


def validate_question(raw: Any, index: int, seen_names: set[str]) -> Question:
    """Validate one question definition; ``seen_names`` collects names for uniqueness.

    Fields are checked in a fixed order (name, flags, type, options, recommendations),
    so the first reported error is stable.
    """
    path = f"questions.{index}"
    if not isinstance(raw, dict):
        _fail(path, "Each question must be an object.")
    _reject_unknown(raw, QUESTION_FIELDS, path)
    name = _question_name(raw, path, seen_names)
    flags = _question_flags(raw, path)
    kind = _question_kind(raw, path)
    options = _question_options(raw, path)
    return Question(
        id=question_id(index),
        name=name,
        kind=kind,
        answers=options,
        recommendations=_question_recommendations(raw, path, len(options)),
        allow_other=flags["allow_other"],
        allow_comments=flags["allow_comments"],
    )


def validate_questionnaire(raw: Any) -> list[Question]:
    """Validate and assign stable IDs to a decoded questionnaire."""
    if not isinstance(raw, dict):
        _fail("$", "The request body must be an object.")
    _reject_unknown(raw, frozenset({"questions"}), "")
    questions_raw = _required(raw, "questions", "")
    if not isinstance(questions_raw, list):
        _fail("questions", "Must be an array.")
    if not MIN_QUESTIONS <= len(questions_raw) <= MAX_QUESTIONS:
        _fail("questions", f"Must contain between {MIN_QUESTIONS} and {MAX_QUESTIONS} questions.")
    names: set[str] = set()
    return [
        validate_question(question_raw, index, names)
        for index, question_raw in enumerate(questions_raw)
    ]
