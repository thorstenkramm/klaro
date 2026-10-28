"""Atomic single-process filesystem persistence, per-token locking, and transitions."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from klaro.answers import SubmittedAnswer
from klaro.clock import Clock, SystemClock
from klaro.config import DEFAULT_LIFETIME_SECONDS
from klaro.models import Question
from klaro.records import InvalidRecord, Questionnaire, Status, generate_token, is_token

LOGGER = logging.getLogger(__name__)


class QuestionnaireNotFound(LookupError):
    """The public token is unknown, pending, expired, deleted, or unreadable."""


class QuestionnaireStateConflict(ValueError):
    """The requested transition is invalid for the current state."""


class UnreadableRecord(ValueError):
    """A stored record cannot be parsed or violates the record schema."""


@dataclass(slots=True)
class _TokenLock:
    lock: threading.RLock = field(default_factory=threading.RLock)
    holders: int = 0


class FileStore:
    """A single-process atomic JSON-file questionnaire store.

    Unreadable records are never served (they behave like unknown tokens), are logged
    once without their token, and are deleted once ``unreadable_retention_seconds``
    have passed since their last modification. No valid record outlives that age, so
    the retention guarantee also covers files that cannot be decoded.
    """

    def __init__(
        self,
        data_dir: Path,
        token_factory: Callable[[], str] = generate_token,
        clock: Clock | None = None,
        *,
        unreadable_retention_seconds: int = DEFAULT_LIFETIME_SECONDS,
    ) -> None:
        self.data_dir = data_dir
        self.clock = clock or SystemClock()
        self.directory = data_dir / "questionnaires"
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.unreadable_retention = timedelta(seconds=unreadable_retention_seconds)
        self._token_factory = token_factory
        self._locks: dict[str, _TokenLock] = {}
        self._locks_guard = threading.Lock()
        self._reported_unreadable: set[str] = set()
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
        if not is_token(token):
            return None
        return self.directory / f"{token}.json"

    def create_pending(
        self,
        *,
        questions: Sequence[Question],
        questioner: str,
        now: datetime | None = None,
        lifetime_seconds: int,
        pushover_request: str | None = None,
    ) -> Questionnaire:
        created_at = now or self.clock.wall()
        record = Questionnaire(
            token=self._token_factory(),
            status=Status.PENDING,
            created_at=created_at,
            expires_at=created_at + timedelta(seconds=lifetime_seconds),
            questioner=questioner,
            questions=tuple(questions),
            pushover_request=pushover_request,
        )
        self.write(record)
        return record

    def read(self, token: str) -> Questionnaire | None:
        """Return the stored record, ``None`` when absent, or raise ``UnreadableRecord``."""
        path = self._path(token)
        if path is None:
            return None
        try:
            with path.open(encoding="utf-8") as handle:
                raw = json.load(handle)
        except FileNotFoundError:
            return None
        except ValueError as exc:  # JSONDecodeError and UnicodeDecodeError
            raise UnreadableRecord(f"Invalid JSON ({type(exc).__name__})") from exc
        try:
            return Questionnaire.from_storage(token, raw)
        except InvalidRecord as exc:
            raise UnreadableRecord(str(exc)) from exc

    def _load(self, token: str) -> Questionnaire | None:
        """Read for request and maintenance paths, treating unreadable records as absent."""
        try:
            return self.read(token)
        except UnreadableRecord as exc:
            self._handle_unreadable(token, exc)
            return None

    def _handle_unreadable(self, token: str, error: UnreadableRecord) -> None:
        path = self._path(token)
        if path is None:
            return
        try:
            modified = datetime.fromtimestamp(path.stat().st_mtime, UTC)
        except FileNotFoundError:
            return
        if self.clock.wall() >= modified + self.unreadable_retention:
            self.delete(token)
            LOGGER.warning("Deleted an unreadable questionnaire record after its retention period")
            return
        if token not in self._reported_unreadable:
            self._reported_unreadable.add(token)
            LOGGER.warning(
                "Ignoring an unreadable questionnaire record (%s); it will be deleted "
                "%d seconds after its last modification",
                error,
                self.unreadable_retention.total_seconds(),
            )

    @contextmanager
    def locked(self, token: str) -> Iterator[None]:
        """Serialize every read-modify-write transition for one token.

        Locks exist only while held or awaited, so arbitrary request paths cannot
        accumulate worker memory.
        """
        with self._locks_guard:
            entry = self._locks.get(token)
            if entry is None:
                entry = self._locks[token] = _TokenLock()
            entry.holders += 1
        try:
            with entry.lock:
                yield
        finally:
            with self._locks_guard:
                entry.holders -= 1
                if entry.holders == 0:
                    del self._locks[token]

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
                record = self._load(token)
                if record is None:
                    continue
                if record.status is Status.PENDING:
                    self.delete(token)
                    removed["pending"] += 1
                elif self._delete_if_expired(record):
                    removed["expired"] += 1
        return removed

    def cleanup_expired(self) -> int:
        removed = 0
        for token in list(self._stored_tokens()):
            with self.locked(token):
                record = self._load(token)
                if record is not None and self._delete_if_expired(record):
                    removed += 1
        return removed

    def _require_live(self, token: str) -> Questionnaire:
        """Load a record under its lock, treating absent or expired records as not found."""
        record = self._load(token)
        if record is None or self._delete_if_expired(record):
            raise QuestionnaireNotFound
        return record

    def get_public(self, token: str) -> Questionnaire:
        if not is_token(token):
            raise QuestionnaireNotFound
        with self.locked(token):
            record = self._require_live(token)
            if record.status is Status.PENDING:
                raise QuestionnaireNotFound
            return record

    def publish(self, token: str, *, pushover_request: str | None = None) -> Questionnaire:
        with self.locked(token):
            record = self._require_live(token)
            if record.status is not Status.PENDING:
                raise QuestionnaireStateConflict("Only a pending questionnaire can be published")
            published = replace(
                record,
                status=Status.AWAITING_ANSWER,
                pushover_request=pushover_request or record.pushover_request,
            )
            self.write(published)
            return published

    def discard_pending(self, token: str) -> None:
        with self.locked(token):
            record = self._load(token)
            if record is None or self._delete_if_expired(record):
                return
            if record.status is Status.PENDING:
                self.delete(token)

    def submit_answers(self, token: str, answers: Mapping[str, SubmittedAnswer]) -> Questionnaire:
        if not is_token(token):
            raise QuestionnaireNotFound
        with self.locked(token):
            record = self._require_live(token)
            if record.status is not Status.AWAITING_ANSWER:
                raise QuestionnaireStateConflict("Questionnaire is not accepting answers")
            submitted = replace(
                record,
                status=Status.ANSWERED,
                answers=dict(answers),
                answered_at=self.clock.wall(),
            )
            self.write(submitted)
            self._notify_transition(token, "answered")
            return submitted

    def confirm(self, token: str) -> Questionnaire:
        if not is_token(token):
            raise QuestionnaireNotFound
        with self.locked(token):
            record = self._require_live(token)
            if record.status is not Status.ANSWERED:
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
        self._reported_unreadable.discard(token)
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
