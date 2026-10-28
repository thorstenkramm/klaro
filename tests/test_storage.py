from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from klaro.answers import SubmittedAnswer
from klaro.filestore import FileStore, UnreadableRecord
from klaro.models import Question
from klaro.records import InvalidRecord, Questionnaire, generate_token

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
TOKEN = "a" * 43
QUESTION = Question(id="q1", name="Drink?", kind="radio", answers=("beer", "water"))


def store(tmp_path: Path) -> FileStore:
    return FileStore(tmp_path / "data", token_factory=lambda: TOKEN)


def pending(tmp_path: Path) -> tuple[FileStore, Questionnaire]:
    target = store(tmp_path)
    record = target.create_pending(
        questions=[QUESTION],
        questioner="Dinner mate",
        now=NOW,
        lifetime_seconds=86_400,
        pushover_request="request-id",
    )
    return target, record


def test_generate_token_uses_256_bit_secrets() -> None:
    with patch("klaro.records.secrets.token_urlsafe", return_value=TOKEN) as factory:
        assert generate_token() == TOKEN
    factory.assert_called_once_with(32)


def test_generated_tokens_are_urlsafe_and_unique() -> None:
    first = generate_token()
    second = generate_token()
    assert len(first) == 43
    assert first != second
    assert "/" not in first
    assert "+" not in first


def test_pending_record_round_trip(tmp_path: Path) -> None:
    target, record = pending(tmp_path)

    loaded = target.read(TOKEN)

    assert loaded == record
    assert loaded is not None
    assert loaded.version == 4
    assert loaded.answered_at is None
    assert loaded.status == "pending"
    assert loaded.expires_at == NOW + timedelta(days=1)
    assert loaded.answers is None
    assert loaded.public_dict()["questions"][0]["answered"] is None
    assert TOKEN not in repr(record)


def test_files_and_directory_have_owner_only_permissions(tmp_path: Path) -> None:
    target, _ = pending(tmp_path)
    path = target.directory / f"{TOKEN}.json"

    assert target.directory.stat().st_mode & 0o777 == 0o700
    assert path.stat().st_mode & 0o777 == 0o600


def test_storage_is_versioned_and_excludes_secrets(tmp_path: Path) -> None:
    target, _ = pending(tmp_path)
    path = target.directory / f"{TOKEN}.json"
    raw_text = path.read_text()
    raw = json.loads(raw_text)

    assert raw["version"] == 4
    assert raw["answered_at"] is None
    assert raw["pushover_request"] == "request-id"
    assert "token" not in raw
    assert TOKEN not in raw_text
    assert "a" * 30 not in raw_text
    assert "b" * 30 not in raw_text


def test_atomic_replace_leaves_no_temporary_files(tmp_path: Path) -> None:
    target, record = pending(tmp_path)
    path = target.directory / f"{TOKEN}.json"
    original = path.read_bytes()
    answered = Questionnaire(
        token=record.token,
        status="answered",
        created_at=record.created_at,
        expires_at=record.expires_at,
        questioner=record.questioner,
        questions=record.questions,
        answers={"q1": SubmittedAnswer(("beer",))},
        answered_at=NOW,
        pushover_request=record.pushover_request,
    )

    with patch("klaro.filestore.os.replace", wraps=os.replace) as replace:
        target.write(answered)
    replace.assert_called_once()
    assert target.read(TOKEN) == answered
    assert original != path.read_bytes()
    assert list(target.directory.glob(".questionnaire-*")) == []


def test_failed_replace_preserves_old_record_and_cleans_temporary(tmp_path: Path) -> None:
    target, record = pending(tmp_path)
    path = target.directory / f"{TOKEN}.json"
    original = path.read_bytes()

    with (
        patch("klaro.filestore.os.replace", side_effect=OSError("simulated")),
        pytest.raises(OSError, match="simulated"),
    ):
        target.write(record)

    assert path.read_bytes() == original
    assert list(target.directory.glob(".questionnaire-*")) == []


def test_delete_is_idempotent_and_path_traversal_is_not_read(tmp_path: Path) -> None:
    target, _ = pending(tmp_path)

    target.delete(TOKEN)
    assert target.read(TOKEN) is None
    target.delete(TOKEN)
    assert target.read("../etc/passwd") is None
    assert target.read("short") is None


@pytest.mark.parametrize("version", [1, 2, 3, 999])
def test_unsupported_record_version_is_rejected(tmp_path: Path, version: int) -> None:
    target, _ = pending(tmp_path)
    path = target.directory / f"{TOKEN}.json"
    raw = json.loads(path.read_text())
    raw["version"] = version
    path.write_text(json.dumps(raw))

    with pytest.raises(UnreadableRecord, match="version"):
        target.read(TOKEN)


@pytest.mark.parametrize(
    ("status", "answers", "timestamp"),
    [
        ("unknown", None, None),
        ("answered", {"q1": ["beer"]}, None),
        ("answered", None, "2026-10-25T12:00:00Z"),
        ("answered", {}, "2026-10-25T12:00:00Z"),
        ("awaiting_answer", None, "2026-10-25T12:00:00Z"),
        ("pending", {"q1": ["beer"]}, None),
        ("answered", {"q1": ["beer"]}, "2026-10-25T12:00:00"),
    ],
)
def test_invalid_state_timestamp_combination_is_rejected(tmp_path, status, answers, timestamp):
    _, record = pending(tmp_path)
    raw = record.storage_dict()
    raw.update(status=status, answers=answers, answered_at=timestamp)
    with pytest.raises(InvalidRecord):
        Questionnaire.from_storage(TOKEN, raw)


def answered_raw(record: Questionnaire, answers: dict) -> dict:
    raw = record.storage_dict()
    raw.update(status="answered", answered_at="2026-10-25T12:00:00Z", answers=answers)
    return raw


def test_rich_answer_round_trip_preserves_text_and_flags(tmp_path: Path) -> None:
    _, record = pending(tmp_path)
    question = Question(
        id="q1",
        name="Drink?",
        kind="radio",
        answers=("beer", "water"),
        allow_other=True,
        allow_comments=True,
    )
    record = Questionnaire(
        token=record.token,
        status=record.status,
        created_at=record.created_at,
        expires_at=record.expires_at,
        questioner=record.questioner,
        questions=(question,),
    )
    answer = {"answered": [], "other": "sparkling", "comment": "no ice"}
    decoded = Questionnaire.from_storage(TOKEN, answered_raw(record, {"q1": answer}))
    assert decoded.answers == {"q1": SubmittedAnswer((), "sparkling", "no ice")}
    assert decoded.questions[0].allow_other is True
    assert decoded.questions[0].allow_comments is True


@pytest.mark.parametrize(
    "answers",
    [
        {},
        {"q1": {"answered": [], "other": None, "comment": None}, "q2": {}},
        {"q1": {"answered": ["beer"], "other": "custom", "comment": None}},
        {"q1": {"answered": [], "other": None, "comment": None}},
        {"q1": {"answered": ["beer", "water"], "other": None, "comment": None}},
        {"q1": {"answered": ["beer", "beer"], "other": None, "comment": None}},
        {"q1": {"answered": ["beer"], "other": None, "comment": "forged"}},
        {"q1": {"answered": "beer", "other": None, "comment": None}},
    ],
)
def test_invalid_rich_answer_invariants_are_rejected(tmp_path: Path, answers: dict) -> None:
    _, record = pending(tmp_path)
    with pytest.raises(InvalidRecord):
        Questionnaire.from_storage(TOKEN, answered_raw(record, answers))


@pytest.mark.parametrize(("field", "value"), [("other", " padded "), ("other", "x" * 2_001)])
def test_disabled_and_invalid_other_text_is_rejected(
    tmp_path: Path, field: str, value: str
) -> None:
    _, record = pending(tmp_path)
    answers = {"q1": {"answered": ["beer"], field: value, "comment": None}}
    with pytest.raises(InvalidRecord):
        Questionnaire.from_storage(TOKEN, answered_raw(record, answers))
