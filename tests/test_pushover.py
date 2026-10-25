from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest
import requests

from klaro.config import PushoverConfig
from klaro.models import Question
from klaro.pushover import (
    PUSHOVER_MESSAGES_URL,
    PushoverClient,
    PushoverError,
    PushoverRecipientRejected,
)

QUESTION = Question(id="q1", name="Drink?", kind="radio", answers=("beer", "water"))


def response(status: int = 200, payload=None) -> Mock:
    result = Mock()
    result.status_code = status
    result.json.return_value = payload if payload is not None else {"status": 1, "request": "req-1"}
    return result


def client(transport) -> PushoverClient:
    return PushoverClient(
        PushoverConfig(app_token="a" * 30, sound="magic", priority=1),
        transport=transport,
    )


def test_notification_content_and_acceptance() -> None:
    transport = Mock(return_value=response())
    adapter = client(transport)
    url = "https://klaro.example.com/" + "t" * 43

    accepted = adapter.send(
        recipient="u" * 30,
        questioner="Dinner mate",
        questions=[QUESTION, QUESTION],
        url=url,
    )

    assert accepted.request_id == "req-1"
    transport.assert_called_once()
    args, kwargs = transport.call_args
    assert args == (PUSHOVER_MESSAGES_URL,)
    assert kwargs["verify"] is True
    assert kwargs["timeout"] == (3.05, 15.0)
    assert kwargs["data"] == {
        "token": "a" * 30,
        "user": "u" * 30,
        "title": "Questionnaire from Dinner mate",
        "message": "Questioner: Dinner mate\nFirst question: Drink?\nTotal questions: 2",
        "url": url,
        "url_title": "Answer questionnaire from Dinner mate",
        "sound": "magic",
        "priority": 1,
    }
    assert "html" not in kwargs["data"]


def test_display_text_is_truncated_but_complete_url_is_preserved() -> None:
    adapter = client(Mock())
    url = "https://klaro.example.com/" + "t" * 400

    fields = adapter.notification_fields(
        questioner="q" * 1000,
        questions=[Question(id="q1", name="n" * 2000, kind="radio", answers=("a", "b"))],
        url=url,
    )

    assert len(fields["title"]) <= 250
    assert len(fields["message"]) <= 1024
    assert len(fields["url_title"]) <= 100
    assert len(fields["url"]) <= 512
    assert fields["url"] == url
    assert fields["message"].endswith("Total questions: 1")
    assert "First question: " in fields["message"]


def test_too_long_complete_url_is_rejected() -> None:
    adapter = client(Mock())
    with pytest.raises(ValueError, match="512"):
        adapter.notification_fields(
            questioner="Dinner mate", questions=[QUESTION], url="https://example.com/" + "x" * 500
        )


@pytest.mark.parametrize(
    "status_code,payload", [(500, {"status": 1}), (200, {"status": 0}), (200, {"status": True})]
)
def test_only_http_200_with_integer_status_one_is_accepted(status_code: int, payload: dict) -> None:
    transport = Mock(return_value=response(status_code, payload))
    with pytest.raises(PushoverError):
        client(transport).send(
            recipient="u" * 30,
            questioner="Dinner mate",
            questions=[QUESTION],
            url="https://klaro.example.com/" + "t" * 43,
        )
    assert transport.call_count == 1


def test_malformed_success_response_is_not_accepted() -> None:
    malformed = response()
    malformed.json.side_effect = ValueError("not JSON")
    transport = Mock(return_value=malformed)
    with pytest.raises(PushoverError, match="malformed"):
        client(transport).send(
            recipient="u" * 30,
            questioner="Dinner mate",
            questions=[QUESTION],
            url="https://klaro.example.com/" + "t" * 43,
        )


def send_once(adapter: PushoverClient) -> None:
    adapter.send(
        recipient="u" * 30,
        questioner="Dinner mate",
        questions=[QUESTION],
        url="https://klaro.example.com/" + "t" * 43,
    )


def test_structured_recipient_rejection_has_its_own_classification() -> None:
    transport = Mock(
        return_value=response(
            400,
            {
                "status": 0,
                "user": "invalid",
                "errors": ["user identifier is invalid"],
                "request": "req-rejected",
            },
        )
    )

    with pytest.raises(PushoverRecipientRejected) as caught:
        send_once(client(transport))

    assert caught.value.code == "recipient_rejected"
    assert caught.value.http_status == 422
    assert transport.call_count == 1
    assert "u" * 30 not in str(caught.value)


@pytest.mark.parametrize(
    "status_code,payload",
    [
        (400, {"status": 0, "token": "invalid", "errors": ["application token is invalid"]}),
        (429, {"status": 0, "errors": ["quota exceeded"]}),
        (400, {"status": 0, "errors": ["priority is invalid"]}),
        (500, {"status": 0, "user": "invalid"}),
        (200, {"status": 0, "user": "invalid"}),
        (400, {"status": 0, "user": 123}),
        (400, ["not", "an", "object"]),
        (200, {"status": "1"}),
    ],
)
def test_other_failures_never_look_like_recipient_rejections(status_code: int, payload) -> None:
    transport = Mock(return_value=response(status_code, payload))

    with pytest.raises(PushoverError) as caught:
        send_once(client(transport))

    assert not isinstance(caught.value, PushoverRecipientRejected)
    assert caught.value.code == "pushover_unavailable"
    assert caught.value.http_status == 502
    assert transport.call_count == 1


@pytest.mark.parametrize("failure", [requests.Timeout("late"), requests.ConnectionError("offline")])
def test_timeouts_and_connection_failures_are_not_retried(
    failure: requests.RequestException,
) -> None:
    transport = Mock(side_effect=failure)

    with pytest.raises(PushoverError) as caught:
        send_once(client(transport))

    assert caught.value.code == "pushover_unavailable"
    assert transport.call_count == 1


def test_outbound_transport_is_bounded_to_two_concurrent_calls() -> None:
    guard = threading.Lock()
    active = 0
    maximum = 0
    calls = 0

    def transport(*args, **kwargs):
        nonlocal active, maximum, calls
        with guard:
            active += 1
            calls += 1
            maximum = max(maximum, active)
        try:
            time.sleep(0.02)
            return response()
        finally:
            with guard:
                active -= 1

    adapter = client(transport)

    def send(_: int) -> None:
        adapter.send(
            recipient="u" * 30,
            questioner="Dinner mate",
            questions=[QUESTION],
            url="https://klaro.example.com/" + "t" * 43,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(send, range(8)))

    assert calls == 8
    assert maximum == 2
