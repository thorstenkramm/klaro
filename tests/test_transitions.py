from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest

from klaro.models import Question
from klaro.storage import (
    FileStore,
    QuestionnaireNotFound,
    QuestionnaireStateConflict,
)
from tests.helpers import FakeClock

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
TOKEN = "t" * 43
QUESTION = Question(id="q1", name="Drink?", kind="radio", answers=("beer", "water"))


def active_store(tmp_path: Path):
    target = FileStore(tmp_path / "data", token_factory=lambda: TOKEN, clock=FakeClock())
    target.create_pending(
        questions=[QUESTION], questioner="Dinner mate", now=NOW, lifetime_seconds=60
    )
    target.publish(TOKEN, pushover_request="request-id")
    return target


def test_pending_is_not_public_until_publication(tmp_path: Path) -> None:
    target = FileStore(tmp_path / "data", token_factory=lambda: TOKEN, clock=FakeClock())
    target.create_pending(
        questions=[QUESTION], questioner="Dinner mate", now=NOW, lifetime_seconds=60
    )

    with pytest.raises(QuestionnaireNotFound):
        target.get_public(TOKEN)
    published = target.publish(TOKEN, pushover_request="request-id")

    assert published.status == "awaiting_answer"
    assert published.pushover_request == "request-id"
    assert target.get_public(TOKEN) == published
    with pytest.raises(QuestionnaireStateConflict):
        target.publish(TOKEN)


def test_discard_only_pending_records(tmp_path: Path) -> None:
    target = FileStore(tmp_path / "data", token_factory=lambda: TOKEN, clock=FakeClock())
    target.create_pending(
        questions=[QUESTION], questioner="Dinner mate", now=NOW, lifetime_seconds=60
    )
    target.discard_pending(TOKEN)
    assert target.read(TOKEN) is None
    target.discard_pending(TOKEN)

    active_store(tmp_path)
    target.discard_pending(TOKEN)
    assert target.read(TOKEN).status == "awaiting_answer"


def test_answer_then_confirm_deletes(tmp_path: Path) -> None:
    target = active_store(tmp_path)

    answered = target.submit_answers(TOKEN, {"q1": ["beer"]})

    assert answered.status == "answered"
    assert answered.answer_dict() == {"q1": ["beer"]}
    assert target.get_public(TOKEN) == answered
    target.confirm(TOKEN)
    assert target.read(TOKEN) is None
    with pytest.raises(QuestionnaireNotFound):
        target.get_public(TOKEN)
    with pytest.raises(QuestionnaireNotFound):
        target.confirm(TOKEN)


def test_confirmation_before_answer_is_conflict(tmp_path: Path) -> None:
    target = active_store(tmp_path)

    with pytest.raises(QuestionnaireStateConflict):
        target.confirm(TOKEN)
    assert target.read(TOKEN).status == "awaiting_answer"


def test_repeated_submission_preserves_original_answers(tmp_path: Path) -> None:
    target = active_store(tmp_path)
    target.submit_answers(TOKEN, {"q1": ["beer"]})

    with pytest.raises(QuestionnaireStateConflict):
        target.submit_answers(TOKEN, {"q1": ["water"]})
    assert target.read(TOKEN).answer_dict() == {"q1": ["beer"]}


def test_concurrent_first_submission_wins_without_partial_records(tmp_path: Path) -> None:
    target = active_store(tmp_path)
    workers = 12
    barrier = threading.Barrier(workers)

    def submit(index: int) -> str:
        barrier.wait()
        try:
            target.submit_answers(TOKEN, {"q1": ["beer" if index % 2 else "water"]})
            return "stored"
        except QuestionnaireStateConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=workers) as pool:
        outcomes = list(pool.map(submit, range(workers)))

    assert outcomes.count("stored") == 1
    assert outcomes.count("conflict") == workers - 1
    record = target.read(TOKEN)
    assert record.status == "answered"
    assert record.answer_dict() in ({"q1": ["beer"]}, {"q1": ["water"]})
    path = target.directory / f"{TOKEN}.json"
    assert json.loads(path.read_text())["status"] == "answered"
    assert list(target.directory.glob(".questionnaire-*")) == []
