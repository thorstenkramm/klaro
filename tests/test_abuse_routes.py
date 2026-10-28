from __future__ import annotations

from unittest.mock import Mock

import pytest

from tests.app_helpers import IP, make_app, post_creation, pushover_response
from tests.helpers import FakeClock


def test_omitted_allowlist_permits_unauthenticated_creation(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, transport = make_app(tmp_path, fake_clock)

    response = post_creation(app.test_client())

    assert response.status_code == 201
    assert transport.call_count == 1


def test_exact_allowlist_value_is_accepted(tmp_path, fake_clock: FakeClock) -> None:
    app, transport = make_app(tmp_path, fake_clock, questioners=("Dinner mate", "Other"))

    assert post_creation(app.test_client()).status_code == 201
    assert transport.call_count == 1


@pytest.mark.parametrize("label", ["dinner mate", "Dinner Mate", " Dinner mate", "Dinner mate "])
def test_case_or_whitespace_mismatch_is_forbidden_without_pushover(
    tmp_path, fake_clock: FakeClock, label: str
) -> None:
    app, transport = make_app(tmp_path, fake_clock, questioners=("Dinner mate",))

    response = post_creation(app.test_client(), questioner=label)

    assert response.status_code == 403
    assert response.json["error"]["code"] == "forbidden"
    assert transport.call_count == 0
    assert list(app.extensions["klaro"].store.directory.iterdir()) == []


def test_explicitly_empty_allowlist_denies_every_label(tmp_path, fake_clock: FakeClock) -> None:
    app, transport = make_app(tmp_path, fake_clock, questioners=())

    assert post_creation(app.test_client()).status_code == 403
    assert transport.call_count == 0


def test_invalid_creation_attempts_consume_route_quota(tmp_path, fake_clock: FakeClock) -> None:
    app, transport = make_app(tmp_path, fake_clock)
    client = app.test_client()

    for _ in range(5):
        assert post_creation(client, body={}).status_code == 400
    limited = post_creation(client)

    assert limited.status_code == 429
    assert limited.json["error"]["code"] == "rate_limited"
    assert limited.headers["Retry-After"] == "60"
    assert transport.call_count == 0


def test_allowlist_rejections_consume_route_quota(tmp_path, fake_clock: FakeClock) -> None:
    app, transport = make_app(tmp_path, fake_clock, questioners=("Allowed",))
    client = app.test_client()

    for _ in range(5):
        assert post_creation(client, questioner="Denied").status_code == 403
    assert post_creation(client, questioner="Allowed").status_code == 429
    assert transport.call_count == 0


def test_upstream_failures_consume_route_quota(tmp_path, fake_clock: FakeClock) -> None:
    transport = Mock(return_value=pushover_response(503, {"status": 0}))
    app, transport = make_app(tmp_path, fake_clock, transport=transport)
    client = app.test_client()

    for _ in range(5):
        assert post_creation(client).status_code == 502
    limited = post_creation(client)

    assert limited.status_code == 429
    assert transport.call_count == 5
    assert list(app.extensions["klaro"].store.directory.iterdir()) == []


def test_backoff_rejections_also_consume_route_quota(tmp_path, fake_clock: FakeClock) -> None:
    transport = Mock(
        return_value=pushover_response(
            400, {"status": 0, "user": "invalid", "errors": ["user identifier is invalid"]}
        )
    )
    app, transport = make_app(tmp_path, fake_clock, transport=transport)
    client = app.test_client()

    assert post_creation(client).status_code == 422
    for _ in range(4):
        blocked = post_creation(client)
        assert blocked.status_code == 429
        assert blocked.json["error"]["code"] == "recipient_backoff"
    limited = post_creation(client)

    assert limited.status_code == 429
    assert limited.json["error"]["code"] == "rate_limited"
    assert transport.call_count == 1


def test_exhausted_creation_quota_does_not_affect_answer_traffic(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    created = post_creation(client)
    token = created.json["url"].rsplit("/", 1)[-1]
    for _ in range(4):
        assert post_creation(client, body={}).status_code == 400
    assert post_creation(client).status_code == 429

    retrieved = client.get(
        f"/{token}", headers={"Accept": "application/json"}, environ_base={"REMOTE_ADDR": IP}
    )
    answered = client.post(
        f"/{token}",
        data={"q1": "1", "q2": ["1", "2"]},
        environ_base={"REMOTE_ADDR": IP},
    )
    polled = client.get(f"/{token}?answer_only=1", environ_base={"REMOTE_ADDR": IP})
    confirmed = client.post(f"/{token}?confirmed=1", environ_base={"REMOTE_ADDR": IP})
    deleted = client.get(f"/{token}", environ_base={"REMOTE_ADDR": IP})

    assert retrieved.status_code == 200
    assert retrieved.json["answered_at"] is None
    assert answered.status_code == 200
    assert polled.status_code == 200
    from tests.response_helpers import expected_answers

    assert polled.json == expected_answers("2026-10-25T12:00:00Z", ["beer"], ["rice", "salad"])
    assert confirmed.status_code == 200
    assert deleted.status_code == 404
    assert deleted.json["error"]["code"] == "not_found"


def test_restart_resets_fixed_window_state(tmp_path, fake_clock: FakeClock) -> None:
    first_app, _ = make_app(tmp_path, fake_clock)
    first_client = first_app.test_client()
    for _ in range(5):
        assert post_creation(first_client, body={}).status_code == 400
    assert post_creation(first_client).status_code == 429

    restarted_app, transport = make_app(tmp_path, fake_clock)

    assert post_creation(restarted_app.test_client()).status_code == 201
    assert transport.call_count == 1


def test_restart_resets_recipient_backoff_state(tmp_path, fake_clock: FakeClock) -> None:
    rejection = Mock(
        return_value=pushover_response(
            400,
            {"status": 0, "user": "invalid", "errors": ["user identifier is invalid"]},
        )
    )
    first_app, _ = make_app(tmp_path, fake_clock, transport=rejection)
    first_client = first_app.test_client()
    assert post_creation(first_client).status_code == 422
    assert post_creation(first_client).status_code == 429

    restarted_app, transport = make_app(tmp_path, fake_clock)

    assert post_creation(restarted_app.test_client()).status_code == 201
    assert transport.call_count == 1
