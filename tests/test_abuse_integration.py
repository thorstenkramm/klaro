from __future__ import annotations

from unittest.mock import Mock

import pytest
import requests

from klaro.abuse import CreationAbuseControls
from klaro.config import PushoverConfig
from klaro.models import Question
from klaro.pushover import PushoverClient, PushoverError, PushoverRecipientRejected
from tests.helpers import FakeClock

IP = "192.0.2.10"
QUESTION = Question(id="q1", name="Drink?", kind="radio", answers=("beer", "water"))
URL = "https://klaro.example.com/" + "t" * 43


def response(status: int, payload) -> Mock:
    result = Mock()
    result.status_code = status
    result.json.return_value = payload
    return result


def adapter(transport) -> PushoverClient:
    return PushoverClient(PushoverConfig(app_token="a" * 30), transport=transport)


def send(client: PushoverClient) -> None:
    client.send(recipient="u" * 30, questioner="Dinner mate", questions=[QUESTION], url=URL)


@pytest.mark.parametrize(
    "failure_response",
    [
        response(400, {"status": 0, "token": "invalid", "errors": ["token is invalid"]}),
        response(429, {"status": 0, "errors": ["quota exceeded"]}),
        response(400, {"status": 0, "errors": ["priority is invalid"]}),
        response(503, {"status": 0}),
        response(200, ["malformed"]),
        response(400, {"status": 0, "user": 123}),
    ],
)
def test_excluded_pushover_response_failures_do_not_trigger_backoff(
    fake_clock: FakeClock, failure_response: Mock
) -> None:
    transport = Mock(return_value=failure_response)
    controls = CreationAbuseControls(fake_clock)
    assert controls.check(IP).allowed

    with pytest.raises(PushoverError) as caught:
        send(adapter(transport))
    assert not isinstance(caught.value, PushoverRecipientRejected)
    controls.record_other_failure(IP)

    assert controls.recipient_backoff.check(IP).allowed
    assert IP not in controls.recipient_backoff._states
    assert transport.call_count == 1


@pytest.mark.parametrize("failure", [requests.Timeout("late"), requests.ConnectionError("offline")])
def test_network_failures_do_not_trigger_backoff(fake_clock: FakeClock, failure: Exception) -> None:
    transport = Mock(side_effect=failure)
    controls = CreationAbuseControls(fake_clock)
    assert controls.check(IP).allowed

    with pytest.raises(PushoverError):
        send(adapter(transport))
    controls.record_other_failure(IP)

    assert controls.recipient_backoff.check(IP).allowed
    assert IP not in controls.recipient_backoff._states


def test_structured_recipient_rejection_integrates_with_backoff(fake_clock: FakeClock) -> None:
    transport = Mock(
        return_value=response(400, {"status": 0, "user": "invalid", "errors": ["user is invalid"]})
    )
    controls = CreationAbuseControls(fake_clock)
    assert controls.check(IP).allowed

    with pytest.raises(PushoverRecipientRejected):
        send(adapter(transport))
    controls.record_recipient_rejection(IP)

    blocked = controls.check(IP)
    assert not blocked.allowed
    assert blocked.code == "recipient_backoff"
    assert blocked.retry_after == 60
    assert transport.call_count == 1


def test_acceptance_resets_next_recipient_rejection_to_one_minute(fake_clock: FakeClock) -> None:
    recipient_rejection = response(
        400, {"status": 0, "user": "invalid", "errors": ["user is invalid"]}
    )
    acceptance = response(200, {"status": 1, "request": "request-id"})
    transport = Mock(side_effect=[recipient_rejection, acceptance, recipient_rejection])
    controls = CreationAbuseControls(fake_clock)
    client = adapter(transport)

    assert controls.check(IP).allowed
    with pytest.raises(PushoverRecipientRejected):
        send(client)
    assert controls.record_recipient_rejection(IP) == 60

    fake_clock.advance(60)
    assert controls.check(IP).allowed
    send(client)
    controls.record_acceptance(IP)

    assert controls.check(IP).allowed
    with pytest.raises(PushoverRecipientRejected):
        send(client)
    assert controls.record_recipient_rejection(IP) == 60
    assert transport.call_count == 3
