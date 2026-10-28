from __future__ import annotations

import json
import time

import pytest

from klaro.sse import RETRY_FRAME, event_frame
from tests.app_helpers import make_app, post_creation
from tests.helpers import FakeClock
from tests.response_helpers import expected_answers


def create_token(client) -> str:
    return post_creation(client).json["url"].rsplit("/", 1)[-1]


def open_stream(client, token: str):
    return client.get(f"/{token}", headers={"Accept": "text/event-stream"}, buffered=False)


def next_frame(stream) -> str:
    frame = next(stream)
    return frame.decode("utf-8") if isinstance(frame, bytes) else frame


def decode_frame(frame: str) -> tuple[str, dict]:
    lines = frame.splitlines()
    assert lines[0].startswith("event: ")
    assert lines[-1] == ""
    event = lines[0][7:]
    data = "\n".join(line[6:] for line in lines[1:] if line.startswith("data: "))
    return event, json.loads(data)


def answer(client, token: str) -> None:
    response = client.post(f"/{token}", data={"q1": "1", "q2": ["1", "2"]})
    assert response.status_code == 200


def test_event_framing_escapes_newlines_and_has_no_event_id() -> None:
    frame = event_frame("heartbeat", {"time": "2026-10-25T12:00:00Z", "text": "a\nb"})

    assert frame.startswith("event: heartbeat\ndata: ")
    assert frame.endswith("\n\n")
    assert "id:" not in frame
    assert len([line for line in frame.splitlines() if line.startswith("data: ")]) == 1
    assert decode_frame(frame)[1]["text"] == "a\nb"


def test_active_stream_has_immediate_status_and_transport_headers(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, _ = make_app(tmp_path, fake_clock, heartbeat_seconds=60)
    client = app.test_client()
    token = create_token(client)

    response = client.get(
        f"/{token}", headers={"Accept": "text/event-stream", "Host": "evil.example"}, buffered=False
    )
    stream = iter(response.response)

    assert response.status_code == 200
    assert response.mimetype == "text/event-stream"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Accel-Buffering"] == "no"
    assert next_frame(stream) == RETRY_FRAME == "retry: 5000\n\n"
    assert decode_frame(next_frame(stream)) == (
        "status",
        {
            "answered_at": None,
            "expires_at": "2026-10-25T12:01:00Z",
            "url": f"https://klaro.example.com/{token}",
        },
    )
    response.close()


def test_answer_arrives_on_open_stream_and_closes_without_polling(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, _ = make_app(tmp_path, fake_clock, heartbeat_seconds=60)
    get_requests = []

    @app.before_request
    def count_get_requests() -> None:
        from flask import request

        if request.method == "GET":
            get_requests.append(request.path)

    client = app.test_client()
    token = create_token(client)
    response = open_stream(client, token)
    stream = iter(response.response)
    assert next_frame(stream) == RETRY_FRAME
    next_frame(stream)

    answer(client, token)

    assert decode_frame(next_frame(stream)) == (
        "answer",
        expected_answers("2026-10-25T12:00:00Z", ["beer"], ["rice", "salad"]),
    )
    with pytest.raises(StopIteration):
        next_frame(stream)
    assert get_requests == [f"/{token}"]
    response.close()


def test_already_answered_stream_immediately_sends_answer_and_closes(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, _ = make_app(tmp_path, fake_clock, heartbeat_seconds=60)
    client = app.test_client()
    token = create_token(client)
    answer(client, token)

    response = open_stream(client, token)
    stream = iter(response.response)

    assert next_frame(stream) == RETRY_FRAME
    assert decode_frame(next_frame(stream)) == (
        "answer",
        expected_answers("2026-10-25T12:00:00Z", ["beer"], ["rice", "salad"]),
    )
    with pytest.raises(StopIteration):
        next_frame(stream)


def test_expiry_is_terminal_and_later_connection_is_404(tmp_path, fake_clock: FakeClock) -> None:
    app, _ = make_app(tmp_path, fake_clock, heartbeat_seconds=60)
    client = app.test_client()
    token = create_token(client)
    response = open_stream(client, token)
    stream = iter(response.response)
    next_frame(stream)
    next_frame(stream)

    fake_clock.advance(60)
    assert app.extensions["klaro"].store.cleanup_expired() == 1

    assert decode_frame(next_frame(stream)) == ("expired", {"expires_at": "2026-10-25T12:01:00Z"})
    with pytest.raises(StopIteration):
        next_frame(stream)
    later = open_stream(client, token)
    assert later.status_code == 404
    assert later.json["error"]["code"] == "not_found"


def test_observable_heartbeat_arrives_on_schedule_and_stream_remains_open(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, _ = make_app(tmp_path, fake_clock, heartbeat_seconds=0.05)
    client = app.test_client()
    token = create_token(client)
    response = open_stream(client, token)
    stream = iter(response.response)
    next_frame(stream)
    next_frame(stream)

    started = time.monotonic()
    heartbeat = decode_frame(next_frame(stream))
    elapsed = time.monotonic() - started

    assert elapsed >= 0.03
    assert heartbeat == ("heartbeat", {"time": "2026-10-25T12:00:00Z"})
    answer(client, token)
    assert decode_frame(next_frame(stream))[0] == "answer"
    response.close()


def test_heartbeats_do_not_extend_retention(tmp_path, fake_clock: FakeClock) -> None:
    app, _ = make_app(tmp_path, fake_clock, heartbeat_seconds=0.02)
    client = app.test_client()
    token = create_token(client)
    response = open_stream(client, token)
    stream = iter(response.response)
    next_frame(stream)
    _, initial = decode_frame(next_frame(stream))

    assert decode_frame(next_frame(stream))[0] == "heartbeat"
    fake_clock.advance(30)
    assert decode_frame(next_frame(stream))[0] == "heartbeat"
    fake_clock.advance(30)

    assert decode_frame(next_frame(stream)) == ("expired", {"expires_at": "2026-10-25T12:01:00Z"})
    assert initial["expires_at"] == "2026-10-25T12:01:00Z"


def token_after_dropped_stream(tmp_path, fake_clock: FakeClock):
    """Create a questionnaire, read its retry and status frames, then drop the stream."""
    app, _ = make_app(tmp_path, fake_clock, heartbeat_seconds=60)
    client = app.test_client()
    token = create_token(client)
    first = open_stream(client, token)
    stream = iter(first.response)
    next_frame(stream)
    next_frame(stream)
    first.close()
    return app, client, token


def test_interrupted_stream_reconnects_to_current_answer_without_replay(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, client, token = token_after_dropped_stream(tmp_path, fake_clock)
    entries = app.extensions["klaro"].subscribers._entries
    assert token not in entries

    answer(client, token)
    reconnected = open_stream(client, token)
    frames = iter(reconnected.response)

    assert next_frame(frames) == RETRY_FRAME
    event, data = decode_frame(next_frame(frames))
    assert event == "answer"
    assert data == expected_answers("2026-10-25T12:00:00Z", ["beer"], ["rice", "salad"])
    assert data == client.get(f"/{token}?answer_only=1").json
    with pytest.raises(StopIteration):
        next_frame(frames)
    assert token not in entries


def test_reconnect_while_still_active_sends_current_status(tmp_path, fake_clock: FakeClock) -> None:
    _app, client, token = token_after_dropped_stream(tmp_path, fake_clock)

    reconnected = open_stream(client, token)
    frames = iter(reconnected.response)
    assert next_frame(frames) == RETRY_FRAME
    assert decode_frame(next_frame(frames)) == (
        "status",
        {
            "answered_at": None,
            "expires_at": "2026-10-25T12:01:00Z",
            "url": f"https://klaro.example.com/{token}",
        },
    )
    reconnected.close()


def test_pending_and_unknown_tokens_do_not_open_streams(tmp_path, fake_clock: FakeClock) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    runtime = app.extensions["klaro"]
    pending = runtime.store.create_pending(
        questions=[], questioner="Dinner mate", lifetime_seconds=60
    )

    pending_response = open_stream(app.test_client(), pending.token)
    unknown_response = open_stream(app.test_client(), "x" * 43)

    assert pending_response.status_code == unknown_response.status_code == 404
    assert pending_response.get_data() == unknown_response.get_data()
