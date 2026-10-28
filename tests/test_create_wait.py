from __future__ import annotations

import logging

import pytest

from tests.app_helpers import IP, QUESTIONER, RECIPIENT, make_app, post_creation, pushover_response
from tests.helpers import FakeClock

SSE = {"Accept": "text/event-stream"}


@pytest.mark.parametrize("content_type", ["application/json", "application/yaml", None])
def test_creation_default_negotiation_retains_201(
    tmp_path, fake_clock: FakeClock, content_type
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    response = app.test_client().post(
        "/",
        json={"questions": [{"name": "Drink?", "type": "radio", "answers": ["beer", "water"]}]},
        headers={
            "X-Pushover-User": RECIPIENT,
            "X-Questioner": QUESTIONER,
            **({"Content-Type": content_type} if content_type else {}),
        },
        environ_base={"REMOTE_ADDR": IP},
    )
    assert response.status_code == 201


@pytest.mark.parametrize(
    "accept",
    [
        None,
        "*/*",
        "text/event-stream;q=0",
        "text/event-stream;q=0.8, application/json;q=0.9",
        "text/event-stream;q=0.8, text/html;q=0.8",
    ],
)
def test_only_explicitly_preferred_sse_redirects(
    tmp_path, fake_clock: FakeClock, accept: str | None
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    headers = {"Accept": accept} if accept is not None else {}
    response = post_creation(app.test_client(), headers=headers)
    assert response.status_code == 201


def test_sse_creation_returns_empty_relative_redirect(tmp_path, fake_clock: FakeClock) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    response = post_creation(app.test_client(), headers=SSE)
    assert response.status_code == 303
    assert response.data == b""
    assert response.headers["Location"] == "/" + "0" * 43


def test_sse_creation_redirect_ignores_host_and_public_origin(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    response = post_creation(app.test_client(), headers={**SSE, "Host": "evil.invalid"})
    assert response.status_code == 303
    assert response.headers["Location"] == "/" + "0" * 43
    assert "evil" not in response.headers["Location"]
    assert response.headers["Cache-Control"] == "no-store"


def test_sse_creation_errors_do_not_redirect(tmp_path, fake_clock: FakeClock) -> None:
    app, transport = make_app(tmp_path, fake_clock, questioners=("Someone else",))
    client = app.test_client()
    rejected = post_creation(client, headers=SSE)
    assert rejected.status_code == 403
    assert "Location" not in rejected.headers
    assert rejected.json["error"]["code"] == "forbidden"
    assert transport.call_count == 0

    oversized = client.post(
        "/",
        data=b"x" * 65_537,
        content_type="application/json",
        headers={**SSE, "X-Pushover-User": RECIPIENT, "X-Questioner": "Someone else"},
        environ_base={"REMOTE_ADDR": IP},
    )
    assert oversized.status_code == 413
    assert "Location" not in oversized.headers


def test_sse_creation_pushover_and_rate_limit_failures_keep_errors(
    tmp_path, fake_clock: FakeClock, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    from unittest.mock import Mock

    transport = Mock(
        return_value=pushover_response(
            400, {"status": 0, "user": "invalid", "errors": ["invalid user"]}
        )
    )
    app, transport = make_app(tmp_path, fake_clock, transport=transport)
    client = app.test_client()
    rejected = post_creation(client, headers=SSE)
    assert rejected.status_code == 422
    assert "Location" not in rejected.headers
    assert rejected.json["error"]["code"] == "recipient_rejected"

    for _ in range(5):
        assert post_creation(client, body={}, headers=SSE, ip="192.0.2.55").status_code == 400
    limited = post_creation(client, headers=SSE, ip="192.0.2.55")
    assert limited.status_code == 429
    assert limited.headers["Retry-After"] == "60"
    assert "Location" not in limited.headers
    assert RECIPIENT not in caplog.text
    assert "0" * 43 not in caplog.text
