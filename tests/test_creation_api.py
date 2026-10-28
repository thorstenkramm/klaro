from __future__ import annotations

import json
from unittest.mock import Mock

import pytest
import requests

from tests.app_helpers import (
    IP,
    QUESTIONER,
    RECIPIENT,
    VALID_BODY,
    make_app,
    post_creation,
    pushover_response,
)
from tests.helpers import FakeClock
from tests.response_helpers import expected_full


def assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status
    assert set(response.json) == {"error"}
    assert response.json["error"]["code"] == code
    assert isinstance(response.json["error"]["message"], str)
    assert set(response.json["error"]) <= {"code", "message", "fields"}


def assert_no_creation_side_effects(app, transport) -> None:
    assert transport.call_count == 0
    assert list(app.extensions["klaro"].store.directory.iterdir()) == []


def test_json_creation_returns_only_absolute_url_and_expiry(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, transport = make_app(tmp_path, fake_clock)

    response = post_creation(app.test_client())

    assert response.status_code == 201
    assert response.json == {
        "url": "https://klaro.example.com/" + "0" * 43,
        "expires_at": "2026-10-25T12:01:00Z",
    }
    assert RECIPIENT not in response.get_data(as_text=True)
    assert "a" * 30 not in response.get_data(as_text=True)
    sent = transport.call_args.kwargs["data"]
    assert sent["user"] == RECIPIENT
    assert sent["token"] == "a" * 30


def test_yaml_creation_has_the_same_questionnaire_structure(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    yaml_body = b"""questions:
  - name: Drink?
    type: radio
    answers: [beer, water]
  - name: Sides?
    type: checkbox
    answers: [rice, salad]
"""

    created = app.test_client().post(
        "/",
        data=yaml_body,
        content_type="application/yaml",
        headers={"X-Pushover-User": RECIPIENT, "X-Questioner": QUESTIONER},
        environ_base={"REMOTE_ADDR": IP},
    )
    token = created.json["url"].rsplit("/", 1)[-1]
    retrieved = app.test_client().get(f"/{token}", headers={"Accept": "application/json"})

    assert created.status_code == 201
    assert retrieved.json == expected_full()


@pytest.mark.parametrize("recipient", [None, "", "short", "a" * 31, "a" * 29 + "-", "a" * 29 + "ä"])
def test_missing_or_invalid_recipient_is_400_without_pushover(
    tmp_path, fake_clock: FakeClock, recipient: str | None
) -> None:
    app, transport = make_app(tmp_path, fake_clock)
    headers = {"X-Questioner": QUESTIONER}
    if recipient is not None:
        headers["X-Pushover-User"] = recipient

    response = app.test_client().post(
        "/",
        data=json.dumps(VALID_BODY),
        content_type="application/json",
        headers=headers,
        environ_base={"REMOTE_ADDR": IP},
    )

    assert_error(response, 400, "invalid_request")
    assert "headers.X-Pushover-User" in response.json["error"]["fields"]
    assert_no_creation_side_effects(app, transport)


@pytest.mark.parametrize("questioner", [None, "", " \t", "x" * 101])
def test_missing_or_invalid_questioner_is_400_without_pushover(
    tmp_path, fake_clock: FakeClock, questioner: str | None
) -> None:
    app, transport = make_app(tmp_path, fake_clock)
    headers = {"X-Pushover-User": RECIPIENT}
    if questioner is not None:
        headers["X-Questioner"] = questioner

    response = app.test_client().post(
        "/",
        data=json.dumps(VALID_BODY),
        content_type="application/json",
        headers=headers,
        environ_base={"REMOTE_ADDR": IP},
    )

    assert_error(response, 400, "invalid_request")
    assert "headers.X-Questioner" in response.json["error"]["fields"]
    assert_no_creation_side_effects(app, transport)


@pytest.mark.parametrize(
    ("body", "content_type"),
    [
        (b"{", "application/json"),
        (b'{"questions": [], "questions": []}', "application/json"),
        (b"questions: [unterminated", "application/yaml"),
        (b"questions: []\nquestions: []", "application/yaml"),
        (b"!!python/object/apply:os.system ['true']", "application/yaml"),
        (b"\xff", "application/json"),
        (b"", "application/json"),
    ],
)
def test_malformed_bodies_are_400_without_pushover(
    tmp_path, fake_clock: FakeClock, body: bytes, content_type: str
) -> None:
    app, transport = make_app(tmp_path, fake_clock)

    response = app.test_client().post(
        "/",
        data=body,
        content_type=content_type,
        headers={"X-Pushover-User": RECIPIENT, "X-Questioner": QUESTIONER},
        environ_base={"REMOTE_ADDR": IP},
    )

    assert_error(response, 400, "invalid_request")
    assert_no_creation_side_effects(app, transport)


@pytest.mark.parametrize(
    "content_type", [None, "text/plain", "application/x-yaml", "application/xml"]
)
def test_unsupported_media_types_are_415_without_pushover(
    tmp_path, fake_clock: FakeClock, content_type: str | None
) -> None:
    app, transport = make_app(tmp_path, fake_clock)
    kwargs = {"data": json.dumps(VALID_BODY)}
    if content_type is not None:
        kwargs["content_type"] = content_type

    response = app.test_client().post(
        "/",
        **kwargs,
        headers={"X-Pushover-User": RECIPIENT, "X-Questioner": QUESTIONER},
        environ_base={"REMOTE_ADDR": IP},
    )

    assert_error(response, 415, "unsupported_media_type")
    assert_no_creation_side_effects(app, transport)


def test_oversized_body_is_413_without_parsing_or_pushover(tmp_path, fake_clock: FakeClock) -> None:
    app, transport = make_app(tmp_path, fake_clock)

    response = app.test_client().post(
        "/",
        data=b"x" * 65_537,
        content_type="application/json",
        headers={"X-Pushover-User": RECIPIENT, "X-Questioner": QUESTIONER},
        environ_base={"REMOTE_ADDR": IP},
    )

    assert_error(response, 413, "payload_too_large")
    assert_no_creation_side_effects(app, transport)


def test_schema_failure_has_field_details_and_no_side_effects(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, transport = make_app(tmp_path, fake_clock)
    body = {"questions": [{"name": "Drink?", "type": "radio", "answers": ["only"]}]}

    response = post_creation(app.test_client(), body=body)

    assert_error(response, 400, "invalid_request")
    assert response.json["error"]["fields"] == {
        "questions.0.answers": ["Must contain between 2 and 50 answer options."]
    }
    assert_no_creation_side_effects(app, transport)


def test_allowlist_failure_is_403_without_pushover(tmp_path, fake_clock: FakeClock) -> None:
    app, transport = make_app(tmp_path, fake_clock, questioners=("Someone else",))

    response = post_creation(app.test_client())

    assert_error(response, 403, "forbidden")
    assert_no_creation_side_effects(app, transport)


def test_duplicate_question_name_has_no_creation_side_effects(tmp_path, fake_clock) -> None:
    app, transport = make_app(tmp_path, fake_clock)
    question = {"name": "Drink?", "type": "radio", "answers": ["beer", "water"]}
    response = post_creation(app.test_client(), body={"questions": [question, question]})
    assert_error(response, 400, "invalid_request")
    assert response.json["error"]["fields"] == {
        "questions.1.name": ["Question names must be unique."]
    }
    assert_no_creation_side_effects(app, transport)


def test_structured_recipient_rejection_is_422_and_cleans_pending(
    tmp_path, fake_clock: FakeClock
) -> None:
    transport = Mock(
        return_value=pushover_response(
            400,
            {"status": 0, "user": "invalid", "errors": ["user identifier is invalid"]},
        )
    )
    app, transport = make_app(tmp_path, fake_clock, transport=transport)

    response = post_creation(app.test_client())

    assert_error(response, 422, "recipient_rejected")
    assert transport.call_count == 1
    assert list(app.extensions["klaro"].store.directory.iterdir()) == []
    assert RECIPIENT not in response.get_data(as_text=True)


@pytest.mark.parametrize("kind", ["server", "quota", "timeout", "connection"])
def test_other_pushover_failures_are_502_and_clean_pending(
    tmp_path, fake_clock: FakeClock, kind: str
) -> None:
    if kind == "timeout":
        transport = Mock(side_effect=requests.Timeout("late"))
    elif kind == "connection":
        transport = Mock(side_effect=requests.ConnectionError("offline"))
    else:
        status = 429 if kind == "quota" else 503
        transport = Mock(
            return_value=pushover_response(status, {"status": 0, "errors": ["failed"]})
        )
    app, transport = make_app(tmp_path, fake_clock, transport=transport)

    response = post_creation(app.test_client())

    assert_error(response, 502, "pushover_unavailable")
    assert transport.call_count == 1
    assert list(app.extensions["klaro"].store.directory.iterdir()) == []


def test_sixth_creation_attempt_is_429_with_retry_after(tmp_path, fake_clock: FakeClock) -> None:
    app, transport = make_app(tmp_path, fake_clock)
    client = app.test_client()
    for _ in range(5):
        post_creation(client, body={})
    fake_clock.advance(43)

    response = post_creation(client)

    assert_error(response, 429, "rate_limited")
    assert response.headers["Retry-After"] == "17"
    assert transport.call_count == 0
