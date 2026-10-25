from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from klaro.models import Question
from klaro.storage import FileStore, Questionnaire, generate_token

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
    with patch("klaro.storage.secrets.token_urlsafe", return_value=TOKEN) as factory:
        assert generate_token() == TOKEN
    factory.assert_called_once_with(32)


def test_generated_tokens_are_urlsafe_and_unique() -> None:
    first = generate_token()
    second = generate_token()
    assert len(first) == 43
    assert first != second
    assert "/" not in first and "+" not in first


def test_pending_record_round_trip(tmp_path: Path) -> None:
    target, record = pending(tmp_path)

    loaded = target.read(TOKEN)

    assert loaded == record
    assert loaded is not None
    assert loaded.version == 1
    assert loaded.status == "pending"
    assert loaded.expires_at == NOW + timedelta(days=1)
    assert loaded.answers is None
    assert loaded.public_dict()["answers"] is None
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

    assert raw["version"] == 1
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
        answers={"q1": ("beer",)},
        pushover_request=record.pushover_request,
    )

    with patch("klaro.storage.os.replace", wraps=os.replace) as replace:
        target.write(answered)
    replace.assert_called_once()
    assert target.read(TOKEN) == answered
    assert original != path.read_bytes()
    assert list(target.directory.glob(".questionnaire-*")) == []


def test_failed_replace_preserves_old_record_and_cleans_temporary(tmp_path: Path) -> None:
    target, record = pending(tmp_path)
    path = target.directory / f"{TOKEN}.json"
    original = path.read_bytes()

    with patch("klaro.storage.os.replace", side_effect=OSError("simulated")):
        with pytest.raises(OSError, match="simulated"):
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


def test_unsupported_record_version_is_rejected(tmp_path: Path) -> None:
    target, _ = pending(tmp_path)
    path = target.directory / f"{TOKEN}.json"
    raw = json.loads(path.read_text())
    raw["version"] = 999
    path.write_text(json.dumps(raw))

    with pytest.raises(ValueError, match="version"):
        target.read(TOKEN)
