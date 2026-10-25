from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from klaro.models import Question
from klaro.storage import FileStore, QuestionnaireNotFound
from klaro.subscribers import SubscriberHub
from tests.helpers import FakeClock

QUESTION = Question(id="q1", name="Drink?", kind="radio", answers=("beer", "water"))


def setup_hub(tmp_path: Path, clock: FakeClock, token: str = "s" * 43):
    store = FileStore(tmp_path / "data", token_factory=lambda: token, clock=clock)
    store.create_pending(questions=[QUESTION], questioner="Dinner mate", lifetime_seconds=60)
    store.publish(token)
    hub = SubscriberHub(store)
    return store, hub


def test_registration_returns_current_active_state(tmp_path: Path, fake_clock: FakeClock) -> None:
    _, hub = setup_hub(tmp_path, fake_clock)

    with hub.register("s" * 43) as subscription:
        assert subscription.initial.status == "awaiting_answer"
        event, record = subscription.wait_for_change(0.01)
        assert event == "heartbeat"
        assert record.status == "awaiting_answer"


def test_answer_notification_reaches_waiting_subscriber(
    tmp_path: Path, fake_clock: FakeClock
) -> None:
    store, hub = setup_hub(tmp_path, fake_clock)

    with hub.register("s" * 43) as subscription:

        def answer() -> None:
            time.sleep(0.02)
            store.submit_answers("s" * 43, {"q1": ["beer"]})

        thread = threading.Thread(target=answer)
        thread.start()
        event, record = subscription.wait_for_change(2)
        thread.join()

        assert event == "answer"
        assert record.answer_dict() == {"q1": ["beer"]}


def test_expiry_notification_reaches_waiting_subscriber(
    tmp_path: Path, fake_clock: FakeClock
) -> None:
    store, hub = setup_hub(tmp_path, fake_clock)

    with hub.register("s" * 43) as subscription:
        fake_clock.advance(60)
        thread = threading.Thread(target=store.cleanup_expired)
        thread.start()
        event, record = subscription.wait_for_change(2)
        thread.join()

        assert event == "expired"
        assert record is None


def test_lazy_expiry_is_seen_without_external_notification(
    tmp_path: Path, fake_clock: FakeClock
) -> None:
    _, hub = setup_hub(tmp_path, fake_clock)

    with hub.register("s" * 43) as subscription:
        fake_clock.advance(60)
        event, record = subscription.wait_for_change(0)
        assert event == "expired"
        assert record is None


def test_already_answered_and_interrupted_reconnect_get_current_state(
    tmp_path: Path, fake_clock: FakeClock
) -> None:
    store, hub = setup_hub(tmp_path, fake_clock)
    subscription = hub.register("s" * 43)
    subscription.close()
    subscription.close()
    store.submit_answers("s" * 43, {"q1": ["water"]})

    with hub.register("s" * 43) as reconnected:
        assert reconnected.initial.status == "answered"
        event, record = reconnected.snapshot()
        assert event == "answer"
        assert record.answer_dict() == {"q1": ["water"]}


def test_expired_questionnaire_cannot_register(tmp_path: Path, fake_clock: FakeClock) -> None:
    _, hub = setup_hub(tmp_path, fake_clock)
    fake_clock.advance(60)

    with pytest.raises(QuestionnaireNotFound):
        hub.register("s" * 43)


def test_register_and_submit_race_never_loses_answer(tmp_path: Path, fake_clock: FakeClock) -> None:
    for index in range(8):
        token = f"{index}" * 43
        store, hub = setup_hub(tmp_path / str(index), fake_clock, token)
        barrier = threading.Barrier(2)
        subscriptions = []

        def register(barrier=barrier, subscriptions=subscriptions, hub=hub, token=token) -> None:
            barrier.wait()
            subscriptions.append(hub.register(token))

        def submit(barrier=barrier, store=store, token=token) -> None:
            barrier.wait()
            store.submit_answers(token, {"q1": ["beer"]})

        first = threading.Thread(target=register)
        second = threading.Thread(target=submit)
        first.start()
        second.start()
        first.join()
        second.join()

        with subscriptions[0] as subscription:
            event, record = subscription.snapshot()
            assert event == "answer"
            assert record.answer_dict() == {"q1": ["beer"]}
