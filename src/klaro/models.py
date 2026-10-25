"""Questionnaire API models and strict input validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class SchemaValidationError(ValueError):
    """A field-aware questionnaire validation failure."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field
        self.message = message
        self.fields = {field: [message]}


@dataclass(frozen=True)
class Question:
    id: str
    name: str
    kind: str
    answers: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.kind,
            "answers": list(self.answers),
        }


def _fail(field: str, message: str) -> None:
    raise SchemaValidationError(field, message)


def _required(mapping: dict[str, Any], key: str, path: str) -> Any:
    if key not in mapping:
        _fail(f"{path}.{key}" if path else key, "This field is required.")
    return mapping[key]


def _reject_unknown(mapping: dict[str, Any], allowed: set[str], path: str) -> None:
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


def validate_questionnaire(raw: Any) -> list[Question]:
    """Validate and assign stable IDs to a decoded questionnaire."""
    if not isinstance(raw, dict):
        _fail("$", "The request body must be an object.")
    _reject_unknown(raw, {"questions"}, "")
    questions_raw = _required(raw, "questions", "")
    if not isinstance(questions_raw, list):
        _fail("questions", "Must be an array.")
    if not 1 <= len(questions_raw) <= 20:
        _fail("questions", "Must contain between 1 and 20 questions.")

    questions: list[Question] = []
    for index, question_raw in enumerate(questions_raw):
        path = f"questions.{index}"
        if not isinstance(question_raw, dict):
            _fail(path, "Each question must be an object.")
        _reject_unknown(question_raw, {"name", "type", "answers"}, path)
        name = _text(_required(question_raw, "name", path), f"{path}.name", 500)
        kind = _required(question_raw, "type", path)
        if kind not in {"radio", "checkbox"}:
            _fail(f"{path}.type", "Must be either radio or checkbox.")
        options_raw = _required(question_raw, "answers", path)
        if not isinstance(options_raw, list):
            _fail(f"{path}.answers", "Must be an array of answer options.")
        if not 2 <= len(options_raw) <= 50:
            _fail(f"{path}.answers", "Must contain between 2 and 50 answer options.")

        options: list[str] = []
        seen: set[str] = set()
        for option_index, option_raw in enumerate(options_raw):
            option_path = f"{path}.answers.{option_index}"
            option = _text(option_raw, option_path, 200)
            if option in seen:
                _fail(option_path, "Answer options must be distinct.")
            seen.add(option)
            options.append(option)
        questions.append(Question(id=f"q{index + 1}", name=name, kind=kind, answers=tuple(options)))
    return questions
