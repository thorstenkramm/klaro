"""Versioned questionnaire records and atomic filesystem persistence."""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import tempfile
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from klaro.clock import Clock, SystemClock
from klaro.models import Question

SCHEMA_VERSION = 1
_TOKEN_PATH_RE = re.compile(r"^[A-Za-z0-9_-]{43}$", re.ASCII)
LOGGER = logging.getLogger(__name__)


def generate_token() -> str:
    """Return a URL-safe token containing 256 bits of randomness."""
    return secrets.token_urlsafe(32)


class QuestionnaireNotFound(LookupError):
    """The public token is unknown, pending, expired, or deleted."""


class QuestionnaireStateConflict(ValueError):
    """The requested transition is invalid for the current state."""


def format_time(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("Questionnaire timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Stored timestamps must include a timezone")
    return parsed.astimezone(UTC)


@dataclass(frozen=True)
class Questionnaire:
    token: str = field(repr=False)
    status: str
    created_at: datetime
    expires_at: datetime
    questioner: str
    questions: tuple[Question, ...]
    answers: dict[str, tuple[str, ...]] | None = None
    pushover_request: str | None = None
    version: int = SCHEMA_VERSION

    def storage_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "status": self.status,
            "created_at": format_time(self.created_at),
            "expires_at": format_time(self.expires_at),
            "questioner": self.questioner,
            "questions": [question.as_dict() for question in self.questions],
            "answers": (
                None
                if self.answers is None
                else {key: list(values) for key, values in self.answers.items()}
            ),
            "pushover_request": self.pushover_request,
        }

    def public_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "expires_at": format_time(self.expires_at),
            "questions": [question.as_dict() for question in self.questions],
            "answers": self.answer_dict(),
        }

    def answer_dict(self) -> dict[str, list[str]] | None:
        if self.answers is None:
            return None
        return {key: list(values) for key, values in self.answers.items()}

    @classmethod
    def from_storage(cls, token: str, raw: dict[str, Any]) -> Questionnaire:
        if raw.get("version") != SCHEMA_VERSION:
            raise ValueError("Unsupported questionnaire record version")
        questions = tuple(
            Question(
                id=item["id"],
                name=item["name"],
                kind=item["type"],
                answers=tuple(item["answers"]),
            )
            for item in raw["questions"]
        )
        answers_raw = raw.get("answers")
        answers = (
            None
            if answers_raw is None
            else {key: tuple(values) for key, values in answers_raw.items()}
        )
        return cls(
            token=token,
            status=raw["status"],
            created_at=parse_time(raw["created_at"]),
            expires_at=parse_time(raw["expires_at"]),
            questioner=raw["questioner"],
            questions=questions,
            answers=answers,
            pushover_request=raw.get("pushover_request"),
            version=raw["version"],
        )


class FileStore:
    """A single-process atomic JSON-file questionnaire store."""

    def __init__(
        self,
        data_dir: Path,
        token_factory: Callable[[], str] = generate_token,
        clock: Clock | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.clock = clock or SystemClock()
        self.directory = data_dir / "questionnaires"
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._token_factory = token_factory
        self._locks: dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()
        self._transition_listeners: list[Callable[[str, str], None]] = []
        self.recover()

    def add_transition_listener(self, listener: Callable[[str, str], None]) -> None:
        """Register a worker-local listener for committed answer/expiry events."""
        self._transition_listeners.append(listener)

    def _notify_transition(self, token: str, event: str) -> None:
        for listener in self._transition_listeners:
            try:
                listener(token, event)
            except Exception:
                LOGGER.exception("Questionnaire transition listener failed")

    def _path(self, token: str) -> Path | None:
        if not _TOKEN_PATH_RE.fullmatch(token):
            return None
        return self.directory / f"{token}.json"

    def create_pending(
        self,
        *,
        questions: list[Question] | tuple[Question, ...],
        questioner: str,
        now: datetime | None = None,
        lifetime_seconds: int,
        pushover_request: str | None = None,
    ) -> Questionnaire:
        created_at = now or self.clock.wall()
        record = Questionnaire(
            token=self._token_factory(),
            status="pending",
            created_at=created_at,
            expires_at=created_at + timedelta(seconds=lifetime_seconds),
            questioner=questioner,
            questions=tuple(questions),
            pushover_request=pushover_request,
        )
        self.write(record)
        return record

    def read(self, token: str) -> Questionnaire | None:
        path = self._path(token)
        if path is None:
            return None
        try:
            with path.open(encoding="utf-8") as handle:
                raw = json.load(handle)
        except FileNotFoundError:
            return None
        return Questionnaire.from_storage(token, raw)

    @contextmanager
    def locked(self, token: str) -> Iterator[None]:
        """Serialize every read-modify-write transition for one token."""
        with self._locks_guard:
            lock = self._locks.setdefault(token, threading.RLock())
        with lock:
            yield

    def _is_expired(self, record: Questionnaire) -> bool:
        return self.clock.wall() >= record.expires_at

    def _delete_if_expired(self, record: Questionnaire) -> bool:
        if not self._is_expired(record):
            return False
        self.delete(record.token)
        self._notify_transition(record.token, "expired")
        return True

    def _stored_tokens(self) -> Iterator[str]:
        for path in self.directory.glob("*.json"):
            if self._path(path.stem) is not None:
                yield path.stem

    def recover(self) -> dict[str, int]:
        """Remove interrupted pending records and records already past expiry."""
        removed = {"pending": 0, "expired": 0}
        for token in list(self._stored_tokens()):
            with self.locked(token):
                try:
                    record = self.read(token)
                except (ValueError, KeyError, json.JSONDecodeError):
                    continue
                if record is None:
                    continue
                if record.status == "pending":
                    self.delete(token)
                    removed["pending"] += 1
                elif self._delete_if_expired(record):
                    removed["expired"] += 1
        return removed

    def cleanup_expired(self) -> int:
        removed = 0
        for token in list(self._stored_tokens()):
            with self.locked(token):
                try:
                    record = self.read(token)
                except (ValueError, KeyError, json.JSONDecodeError):
                    continue
                if record is not None and self._delete_if_expired(record):
                    removed += 1
        return removed

    def get_public(self, token: str) -> Questionnaire:
        with self.locked(token):
            record = self.read(token)
            if record is None or record.status == "pending":
                raise QuestionnaireNotFound
            if self._delete_if_expired(record):
                raise QuestionnaireNotFound
            return record

    def publish(self, token: str, *, pushover_request: str | None = None) -> Questionnaire:
        with self.locked(token):
            record = self.read(token)
            if record is None:
                raise QuestionnaireNotFound
            if self._delete_if_expired(record):
                raise QuestionnaireNotFound
            if record.status != "pending":
                raise QuestionnaireStateConflict("Only a pending questionnaire can be published")
            published = replace(
                record,
                status="awaiting_answer",
                pushover_request=pushover_request or record.pushover_request,
            )
            self.write(published)
            return published

    def discard_pending(self, token: str) -> None:
        with self.locked(token):
            record = self.read(token)
            if record is None:
                return
            if self._delete_if_expired(record):
                return
            if record.status == "pending":
                self.delete(token)

    def submit_answers(
        self, token: str, answers: dict[str, tuple[str, ...] | list[str]]
    ) -> Questionnaire:
        with self.locked(token):
            record = self.read(token)
            if record is None:
                raise QuestionnaireNotFound
            if self._delete_if_expired(record):
                raise QuestionnaireNotFound
            if record.status != "awaiting_answer":
                raise QuestionnaireStateConflict("Questionnaire is not accepting answers")
            submitted = replace(
                record,
                status="answered",
                answers={key: tuple(values) for key, values in answers.items()},
            )
            self.write(submitted)
            self._notify_transition(token, "answered")
            return submitted

    def confirm(self, token: str) -> Questionnaire:
        with self.locked(token):
            record = self.read(token)
            if record is None:
                raise QuestionnaireNotFound
            if self._delete_if_expired(record):
                raise QuestionnaireNotFound
            if record.status != "answered":
                raise QuestionnaireStateConflict("Only an answered questionnaire can be confirmed")
            self.delete(token)
            return record

    def write(self, record: Questionnaire) -> None:
        path = self._path(record.token)
        if path is None:
            raise ValueError("Invalid questionnaire token")
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.directory,
                prefix=".questionnaire-",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                os.chmod(handle.name, 0o600)
                json.dump(record.storage_dict(), handle, ensure_ascii=False, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
            temporary_path = None
            self._sync_directory()
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def delete(self, token: str) -> None:
        path = self._path(token)
        if path is None:
            return
        try:
            path.unlink()
        except FileNotFoundError:
            return
        self._sync_directory()

    def _sync_directory(self) -> None:
        descriptor = os.open(self.directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
