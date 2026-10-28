from __future__ import annotations

import threading
from pathlib import Path

import pytest

from klaro.answers import SubmittedAnswer
from klaro.filestore import FileStore, QuestionnaireNotFound
from klaro.models import Question
from klaro.scheduler import CleanupScheduler
from tests.helpers import FakeClock
from tests.response_helpers import selected_by_id

QUESTION = Question(id="q1", name="Drink?", kind="radio", answers=("beer", "water"))
TOKENS = iter(["a" * 43, "b" * 43, "c" * 43])


def make_store(tmp_path: Path, clock: FakeClock, tokens=None) -> FileStore:
    def factory():
        return next(tokens or TOKENS)

    return FileStore(tmp_path / "data", token_factory=factory, clock=clock)


def create(target: FileStore, *, status: str = "awaiting_answer", lifetime: int = 60):
    record = target.create_pending(
        questions=[QUESTION], questioner="Dinner mate", lifetime_seconds=lifetime
    )
    if status != "pending":
        target.publish(record.token)
    if status == "answered":
        target.submit_answers(record.token, {"q1": SubmittedAnswer(("beer",))})
    return target.read(record.token)


def test_creation_uses_injected_wall_clock(tmp_path: Path, fake_clock: FakeClock) -> None:
    target = make_store(tmp_path, fake_clock, iter(["d" * 43]))
    record = create(target, status="pending", lifetime=60)

    assert record.created_at == fake_clock.wall()
    assert record.expires_at.timestamp() - record.created_at.timestamp() == 60


def test_lazy_active_expiry_does_not_extend_on_reads(tmp_path: Path, fake_clock: FakeClock) -> None:
    target = make_store(tmp_path, fake_clock, iter(["d" * 43]))
    record = create(target, lifetime=60)

    fake_clock.advance(30)
    assert target.get_public(record.token).expires_at == record.expires_at
    fake_clock.advance(30)
    with pytest.raises(QuestionnaireNotFound):
        target.get_public(record.token)
    assert target.read(record.token) is None


def test_lazy_answered_expiry(tmp_path: Path, fake_clock: FakeClock) -> None:
    target = make_store(tmp_path, fake_clock, iter(["d" * 43]))
    record = create(target, status="answered", lifetime=60)

    fake_clock.advance(60)
    with pytest.raises(QuestionnaireNotFound):
        target.confirm(record.token)
    assert target.read(record.token) is None


def test_submission_and_publication_after_expiry_are_rejected(
    tmp_path: Path, fake_clock: FakeClock
) -> None:
    active = make_store(tmp_path / "active", fake_clock, iter(["e" * 43]))
    answered = create(active, lifetime=60)
    fake_clock.advance(60)
    with pytest.raises(QuestionnaireNotFound):
        active.submit_answers(answered.token, {"q1": SubmittedAnswer(("beer",))})

    pending_clock = FakeClock()
    pending_store = make_store(tmp_path / "pending", pending_clock, iter(["f" * 43]))
    pending = create(pending_store, status="pending", lifetime=60)
    pending_clock.advance(60)
    with pytest.raises(QuestionnaireNotFound):
        pending_store.publish(pending.token)


def test_cleanup_removes_active_and_answered_without_access(
    tmp_path: Path, fake_clock: FakeClock
) -> None:
    target = make_store(tmp_path, fake_clock, iter(["g" * 43, "h" * 43]))
    create(target, lifetime=60)
    create(target, status="answered", lifetime=60)

    fake_clock.advance(60)
    assert target.cleanup_expired() == 2
    assert list(target.directory.glob("*.json")) == []


def test_restart_recovers_state_and_removes_stale_pending(
    tmp_path: Path, fake_clock: FakeClock
) -> None:
    tokens = iter(["i" * 43, "j" * 43, "k" * 43])
    target = make_store(tmp_path, fake_clock, tokens)
    pending = create(target, status="pending", lifetime=300)
    expired = create(target, lifetime=60)
    surviving = create(target, status="answered", lifetime=300)
    original_expiry = surviving.expires_at

    fake_clock.advance(120)
    restarted = FileStore(tmp_path / "data", clock=fake_clock)

    assert restarted.read(pending.token) is None
    assert restarted.read(expired.token) is None
    recovered = restarted.read(surviving.token)
    assert recovered.status == "answered"
    assert selected_by_id(recovered) == {"q1": ["beer"]}
    assert recovered.expires_at == original_expiry


def test_scheduler_cleans_without_access_and_starts_once(
    tmp_path: Path, fake_clock: FakeClock
) -> None:
    target = make_store(tmp_path, fake_clock, iter(["l" * 43]))
    record = create(target, lifetime=60)
    expired = threading.Event()
    target.add_transition_listener(
        lambda token, event: event == "expired" and token == record.token and expired.set()
    )
    scheduler = CleanupScheduler(target, interval_seconds=0.02)
    scheduler.start()
    first_thread = scheduler._thread
    scheduler.start()
    fake_clock.advance(60)
    try:
        assert scheduler._thread is first_thread
        assert expired.wait(timeout=2)
        assert target.read(record.token) is None
        assert scheduler.running
    finally:
        scheduler.stop()
    assert not scheduler.running
    scheduler.stop()
