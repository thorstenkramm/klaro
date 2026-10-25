from __future__ import annotations

import json
from unittest.mock import Mock

from flask import request

from tests.app_helpers import IP, QUESTIONER, RECIPIENT, VALID_BODY, make_app, pushover_response
from tests.helpers import FakeClock

QUESTIONS = [
    {"id": "q1", "name": "Drink?", "type": "radio", "answers": ["beer", "water"]},
    {
        "id": "q2",
        "name": "Sides?",
        "type": "checkbox",
        "answers": ["rice", "salad"],
    },
]
ANSWERS = {"q1": ["beer"], "q2": ["rice", "salad"]}


def next_text(stream) -> str:
    value = next(stream)
    return value.decode() if isinstance(value, bytes) else value


def expected_storage(token: str, status: str, request_id: str, answers=None) -> str:
    return json.dumps(
        {
            "version": 1,
            "status": status,
            "created_at": "2026-10-25T12:00:00Z",
            "expires_at": "2026-10-25T12:01:00Z",
            "questioner": QUESTIONER,
            "questions": QUESTIONS,
            "answers": answers,
            "pushover_request": request_id,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def assert_stored(app, token: str, status: str, request_id: str, answers=None) -> str:
    runtime = app.extensions["klaro"]
    path = runtime.store.directory / f"{token}.json"
    expected = expected_storage(token, status, request_id, answers)
    assert path.read_text() == expected
    assert list(runtime.store.directory.iterdir()) == [path]
    assert RECIPIENT not in expected
    assert "a" * 30 not in expected
    return expected


def assert_confirmation_and_generic_404(client, token: str) -> None:
    confirmed = client.post(f"/{token}?confirmed=1")
    assert confirmed.status_code == 200
    assert confirmed.json == {"status": "confirmed"}
    deleted = client.get(f"/{token}")
    unknown = client.get("/" + "x" * 43)
    assert deleted.status_code == unknown.status_code == 404
    assert deleted.get_data() == unknown.get_data()
    assert deleted.json == {"error": {"code": "not_found", "message": "Questionnaire not found."}}


def test_json_sse_journey_has_exact_storage_and_no_answer_polling(
    tmp_path, fake_clock: FakeClock
) -> None:
    transport = Mock(
        return_value=pushover_response(200, {"status": 1, "request": "json-request-id"})
    )
    app, transport = make_app(tmp_path, fake_clock, transport=transport, heartbeat_seconds=60)
    client = app.test_client()
    retrieval_requests = []

    @app.before_request
    def count_retrievals() -> None:
        if request.method == "GET":
            retrieval_requests.append((request.path, dict(request.args)))

    created = client.post(
        "/",
        data=json.dumps(VALID_BODY),
        content_type="application/json",
        headers={"X-Pushover-User": RECIPIENT, "X-Questioner": QUESTIONER},
        environ_base={"REMOTE_ADDR": IP},
    )

    assert created.status_code == 201
    assert created.json == {
        "url": "https://klaro.example.com/" + "0" * 43,
        "expires_at": "2026-10-25T12:01:00Z",
    }
    token = created.json["url"].rsplit("/", 1)[-1]
    assert_stored(app, token, "awaiting_answer", "json-request-id")
    assert transport.call_count == 1
    outbound = transport.call_args.kwargs["data"]
    assert outbound["url"] == created.json["url"]
    assert outbound["message"] == (
        "Questioner: Dinner mate\nFirst question: Drink?\nTotal questions: 2"
    )

    stream_response = client.get(
        f"/{token}", headers={"Accept": "text/event-stream"}, buffered=False
    )
    stream = iter(stream_response.response)
    assert next_text(stream) == "retry: 5000\n\n"
    assert next_text(stream) == (
        'event: status\ndata: {"status":"awaiting_answer","expires_at":"2026-10-25T12:01:00Z"}\n\n'
    )

    answered = client.post(f"/{token}", data={"q1": "beer", "q2": ["rice", "salad"]})
    assert answered.status_code == 200
    assert "Answer stored" in answered.text
    assert_stored(app, token, "answered", "json-request-id", ANSWERS)
    assert next_text(stream) == (
        "event: answer\n"
        'data: {"status":"answered","answers":{"q1":["beer"],"q2":["rice","salad"]}}\n\n'
    )
    try:
        next(stream)
        raise AssertionError("SSE stream did not close after the answer")
    except StopIteration:
        pass
    assert retrieval_requests == [(f"/{token}", {})]
    stream_response.close()

    assert_confirmation_and_generic_404(client, token)
    assert app.extensions["klaro"].store.read(token) is None
    assert list(app.extensions["klaro"].store.directory.iterdir()) == []
    assert transport.call_count == 1


def test_yaml_polling_journey_is_exact_and_non_destructive(tmp_path, fake_clock: FakeClock) -> None:
    transport = Mock(
        return_value=pushover_response(200, {"status": 1, "request": "yaml-request-id"})
    )
    app, transport = make_app(tmp_path, fake_clock, transport=transport)
    client = app.test_client()
    yaml_body = b"""questions:
  - name: Drink?
    type: radio
    answers: [beer, water]
  - name: Sides?
    type: checkbox
    answers: [rice, salad]
"""
    created = client.post(
        "/",
        data=yaml_body,
        content_type="application/yaml",
        headers={"X-Pushover-User": RECIPIENT, "X-Questioner": QUESTIONER},
        environ_base={"REMOTE_ADDR": IP},
    )
    assert created.status_code == 201
    token = created.json["url"].rsplit("/", 1)[-1]
    assert_stored(app, token, "awaiting_answer", "yaml-request-id")

    not_ready = client.get(f"/{token}?answer_only=1")
    assert not_ready.status_code == 200
    assert not_ready.json == {"status": "awaiting_answer", "answers": None}
    assert client.post(f"/{token}", data={"q1": "beer", "q2": ["rice", "salad"]}).status_code == 200
    answered_storage = assert_stored(app, token, "answered", "yaml-request-id", ANSWERS)

    first = client.get(f"/{token}?answer_only=1")
    after_first = (app.extensions["klaro"].store.directory / f"{token}.json").read_text()
    second = client.get(f"/{token}?answer_only=1")
    after_second = (app.extensions["klaro"].store.directory / f"{token}.json").read_text()

    assert first.status_code == second.status_code == 200
    assert first.json == second.json == {"status": "answered", "answers": ANSWERS}
    assert first.get_data() == second.get_data()
    assert after_first == after_second == answered_storage
    assert transport.call_count == 1

    assert_confirmation_and_generic_404(client, token)
    assert app.extensions["klaro"].store.read(token) is None
    assert list(app.extensions["klaro"].store.directory.iterdir()) == []
