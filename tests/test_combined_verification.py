from __future__ import annotations

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest

from tests.app_helpers import RECIPIENT, make_app, post_creation, pushover_response
from tests.helpers import FakeClock

RATE_IP = "192.0.2.50"
BACKOFF_IP = "192.0.2.60"
BACKOFF_RECIPIENT = "b" * 30


def open_stream(client, token: str):
    return client.get(f"/{token}", headers={"Accept": "text/event-stream"}, buffered=False)


def next_text(stream) -> str:
    value = next(stream)
    return value.decode() if isinstance(value, bytes) else value


def event(frame: str) -> tuple[str, dict]:
    lines = frame.splitlines()
    return lines[0].removeprefix("event: "), json.loads(
        "\n".join(line.removeprefix("data: ") for line in lines[1:] if line)
    )


def consume_initial(response) -> tuple[object, str, dict]:
    stream = iter(response.response)
    assert next_text(stream) == "retry: 5000\n\n"
    name, data = event(next_text(stream))
    return stream, name, data


def test_combined_restart_streams_expiry_controls_concurrency_and_logs(
    tmp_path, fake_clock: FakeClock, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)

    def transport(*args, **kwargs):
        if kwargs["data"]["user"] == BACKOFF_RECIPIENT:
            return pushover_response(
                400,
                {"status": 0, "user": "invalid", "errors": ["user identifier is invalid"]},
            )
        return pushover_response(200, {"status": 1, "request": "combined-request-id"})

    outbound = Mock(side_effect=transport)
    first_app, outbound = make_app(tmp_path, fake_clock, transport=outbound, heartbeat_seconds=0.02)
    first_client = first_app.test_client()
    first_token = post_creation(first_client).json["url"].rsplit("/", 1)[-1]
    second_token = post_creation(first_client).json["url"].rsplit("/", 1)[-1]
    original = first_app.extensions["klaro"].store.read(first_token)

    interrupted = open_stream(first_client, first_token)
    consume_initial(interrupted)
    interrupted.close()

    for _ in range(5):
        assert post_creation(first_client, body={}, ip=RATE_IP).status_code == 400
    assert post_creation(first_client, ip=RATE_IP).status_code == 429
    assert (
        post_creation(first_client, ip=BACKOFF_IP, recipient=BACKOFF_RECIPIENT).status_code == 422
    )
    assert (
        post_creation(first_client, ip=BACKOFF_IP, recipient=BACKOFF_RECIPIENT).status_code == 429
    )

    restarted, _ = make_app(tmp_path, fake_clock, heartbeat_seconds=0.02)
    restarted_client = restarted.test_client()
    recovered = restarted.extensions["klaro"].store.read(first_token)
    assert recovered.status == "awaiting_answer"
    assert recovered.expires_at == original.expires_at
    assert restarted.extensions["klaro"].abuse.check(RATE_IP).allowed
    assert restarted.extensions["klaro"].abuse.check(BACKOFF_IP).allowed

    first_open = open_stream(restarted_client, first_token)
    first_stream, name, data = consume_initial(first_open)
    assert name == "status"
    assert data == {"status": "awaiting_answer", "expires_at": "2026-10-25T12:01:00Z"}
    second_open = open_stream(restarted_client, first_token)
    second_stream, second_name, _ = consume_initial(second_open)
    assert second_name == "status"

    started = time.monotonic()
    heartbeat_name, heartbeat = event(next_text(first_stream))
    assert time.monotonic() - started >= 0.01
    assert heartbeat_name == "heartbeat"
    assert heartbeat == {"time": "2026-10-25T12:00:00Z"}
    assert restarted_client.get(f"/{first_token}?answer_only=1").status_code == 200
    assert restarted_client.get("/static/vendor/htmx/htmx.min.js").status_code == 200

    barrier = threading.Barrier(2)

    def submit(choice: str) -> int:
        client = restarted.test_client()
        barrier.wait()
        response = client.post(
            f"/{first_token}",
            data={"q1": choice, "q2": "rice" if choice == "beer" else "salad"},
        )
        return response.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(submit, ["beer", "water"]))

    assert sorted(statuses) == [200, 409]
    answered = restarted.extensions["klaro"].store.read(first_token)
    assert answered.answer_dict() in (
        {"q1": ["beer"], "q2": ["rice"]},
        {"q1": ["water"], "q2": ["salad"]},
    )
    for stream in (first_stream, second_stream):
        name, data = event(next_text(stream))
        assert name == "answer"
        assert data == {"status": "answered", "answers": answered.answer_dict()}
        with pytest.raises(StopIteration):
            next(stream)
    first_open.close()
    second_open.close()

    final_app, _ = make_app(tmp_path, fake_clock, heartbeat_seconds=0.02)
    final_client = final_app.test_client()
    final_record = final_app.extensions["klaro"].store.read(first_token)
    assert final_record.status == "answered"
    assert final_record.answer_dict() == answered.answer_dict()
    assert final_record.expires_at == original.expires_at

    answered_stream_response = open_stream(final_client, first_token)
    answered_stream, name, data = consume_initial(answered_stream_response)
    assert name == "answer"
    assert data == {"status": "answered", "answers": answered.answer_dict()}
    with pytest.raises(StopIteration):
        next(answered_stream)

    expiring_response = open_stream(final_client, second_token)
    expiring_stream, name, data = consume_initial(expiring_response)
    assert name == "status"
    assert data["expires_at"] == "2026-10-25T12:01:00Z"
    fake_clock.advance(60)
    assert final_app.extensions["klaro"].store.cleanup_expired() == 2
    assert event(next_text(expiring_stream)) == ("expired", {"status": "expired"})
    with pytest.raises(StopIteration):
        next(expiring_stream)
    expiring_response.close()

    expired = final_client.get(f"/{second_token}")
    unknown = final_client.get("/" + "x" * 43)
    assert expired.status_code == unknown.status_code == 404
    assert expired.get_data() == unknown.get_data()

    for secret in (first_token, second_token, RECIPIENT, BACKOFF_RECIPIENT, "a" * 30):
        assert secret not in caplog.text
    assert "/<redacted>" in caplog.text
    assert outbound.call_count == 3
