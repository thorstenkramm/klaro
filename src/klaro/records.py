"""Versioned questionnaire records: tokens, timestamps, encoding, and public projections."""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from klaro.answers import SubmittedAnswer, is_consistent_answer
from klaro.models import Question, question_id, validate_question

SCHEMA_VERSION = 4
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{43}$", re.ASCII)


class InvalidRecord(ValueError):
    """A stored record is malformed or violates the current record rules."""


class Status(StrEnum):
    PENDING = "pending"
    AWAITING_ANSWER = "awaiting_answer"
    ANSWERED = "answered"


def generate_token() -> str:
    """Return a URL-safe token containing 256 bits of randomness."""
    return secrets.token_urlsafe(32)


def is_token(value: str) -> bool:
    """Return whether a value has the exact shape of a generated questionnaire token."""
    return _TOKEN_RE.fullmatch(value) is not None


def format_time(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("Questionnaire timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Stored timestamps must include a timezone")
    return parsed.astimezone(UTC)


def _optional_time(value: datetime | None) -> str | None:
    return None if value is None else format_time(value)


def _decode_question(index: int, raw: Any, seen_names: set[str]) -> Question:
    """Decode a stored question through the same validator used for client input."""
    if not isinstance(raw, dict) or raw.get("id") != question_id(index):
        raise ValueError("Invalid stored question identifier")
    definition = {key: value for key, value in raw.items() if key != "id"}
    question = validate_question(definition, index, seen_names)
    if question.as_dict() != raw:
        raise ValueError("Stored question is not in canonical form")
    return question


def _decode_answer(question: Question, raw: Any) -> SubmittedAnswer:
    if not isinstance(raw, dict) or set(raw) != {"answered", "other", "comment"}:
        raise ValueError("Invalid stored answer shape")
    if not isinstance(raw["answered"], list):
        raise TypeError("Invalid stored offered answers")
    answer = SubmittedAnswer(tuple(raw["answered"]), raw["other"], raw["comment"])
    if not is_consistent_answer(question, answer):
        raise ValueError("Invalid stored answer")
    return answer


@dataclass(frozen=True, slots=True)
class Questionnaire:
    token: str = field(repr=False)
    status: Status
    created_at: datetime
    expires_at: datetime
    questioner: str
    questions: tuple[Question, ...]
    answers: dict[str, SubmittedAnswer] | None = None
    answered_at: datetime | None = None
    pushover_request: str | None = None
    version: int = SCHEMA_VERSION

    def storage_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "status": str(self.status),
            "created_at": format_time(self.created_at),
            "expires_at": format_time(self.expires_at),
            "questioner": self.questioner,
            "questions": [question.as_dict() for question in self.questions],
            "answers": (
                None
                if self.answers is None
                else {
                    key: {
                        "answered": list(value.answered),
                        "other": value.other,
                        "comment": value.comment,
                    }
                    for key, value in self.answers.items()
                }
            ),
            "answered_at": _optional_time(self.answered_at),
            "pushover_request": self.pushover_request,
        }

    def public_dict(self) -> dict[str, Any]:
        return {
            "expires_at": format_time(self.expires_at),
            "answered_at": _optional_time(self.answered_at),
            "questions": [
                {
                    **self._question_answer(question),
                    "type": str(question.kind),
                    "answers": list(question.answers),
                    "allow_other": question.allow_other,
                    "allow_comments": question.allow_comments,
                }
                for question in self.questions
            ],
        }

    def _question_answer(self, question: Question) -> dict[str, Any]:
        answer = None if self.answers is None else self.answers[question.id]
        return {
            "name": question.name,
            "answered": None if answer is None else list(answer.answered),
            "other": None if answer is None else answer.other,
            "comment": None if answer is None else answer.comment,
            "recommendations": list(question.recommendations),
        }

    def answer_only_dict(self) -> dict[str, Any]:
        return {
            "answered_at": _optional_time(self.answered_at),
            "questions": [self._question_answer(question) for question in self.questions],
        }

    @classmethod
    def from_storage(cls, token: str, raw: Any) -> Questionnaire:
        """Decode a stored record; any malformed content raises ``InvalidRecord``."""
        try:
            return cls._decode(token, raw)
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise InvalidRecord(f"{type(exc).__name__}: {exc}") from exc

    @classmethod
    def _decode(cls, token: str, raw: Any) -> Questionnaire:
        if not isinstance(raw, dict) or raw.get("version") != SCHEMA_VERSION:
            raise ValueError("Unsupported questionnaire record version")
        if not isinstance(raw["questions"], list):
            raise TypeError("Stored questions must be a list")
        names: set[str] = set()
        questions = tuple(
            _decode_question(index, item, names) for index, item in enumerate(raw["questions"])
        )
        answers_raw = raw.get("answers")
        answered_at_raw = raw["answered_at"]
        status = Status(raw["status"])
        if status is Status.ANSWERED:
            if (
                not isinstance(answers_raw, dict)
                or not answers_raw
                or not isinstance(answered_at_raw, str)
            ):
                raise ValueError("Answered records require answers and an answer timestamp")
        elif answers_raw is not None or answered_at_raw is not None:
            raise ValueError("Unanswered records cannot contain answers or an answer timestamp")
        answers = None
        if answers_raw is not None:
            if set(answers_raw) != {question.id for question in questions}:
                raise ValueError("Stored answers must match every question")
            answers = {
                question.id: _decode_answer(question, answers_raw[question.id])
                for question in questions
            }
        return cls(
            token=token,
            status=status,
            created_at=parse_time(raw["created_at"]),
            expires_at=parse_time(raw["expires_at"]),
            questioner=raw["questioner"],
            questions=questions,
            answers=answers,
            answered_at=None if answered_at_raw is None else parse_time(answered_at_raw),
            pushover_request=raw.get("pushover_request"),
            version=raw["version"],
        )
