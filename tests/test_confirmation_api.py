from __future__ import annotations

from tests.app_helpers import make_app, post_creation
from tests.helpers import FakeClock


def create_token(client) -> str:
    return post_creation(client).json["url"].rsplit("/", 1)[-1]


def answer(client, token: str) -> None:
    response = client.post(f"/{token}", data={"q1": "beer", "q2": "rice"})
    assert response.status_code == 200


def test_confirmation_before_answer_is_409_and_preserves_active_record(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = create_token(client)

    response = client.post(f"/{token}?confirmed=1")

    assert response.status_code == 409
    assert response.json["error"]["code"] == "state_conflict"
    assert app.extensions["klaro"].store.read(token).status == "awaiting_answer"
    answer(client, token)


def test_successful_confirmation_deletes_and_repetition_is_generic_404(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = create_token(client)
    answer(client, token)

    confirmed = client.post(f"/{token}?confirmed=1")
    repeated = client.post(f"/{token}?confirmed=1")
    unknown = client.post(f"/{'x' * 43}?confirmed=1")

    assert confirmed.status_code == 200
    assert confirmed.json == {"status": "confirmed"}
    assert token not in confirmed.get_data(as_text=True)
    assert app.extensions["klaro"].store.read(token) is None
    assert repeated.status_code == unknown.status_code == 404
    assert repeated.get_data() == unknown.get_data()
    assert repeated.json["error"]["code"] == "not_found"


def test_get_with_confirmed_parameter_never_mutates_active_or_answered_state(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = create_token(client)

    active = client.get(f"/{token}?confirmed=1", headers={"Accept": "application/json"})
    assert active.status_code == 200
    assert active.json["status"] == "awaiting_answer"
    assert app.extensions["klaro"].store.read(token).status == "awaiting_answer"

    answer(client, token)
    answered = client.get(
        f"/{token}?confirmed=1&answer_only=1", headers={"Accept": "application/json"}
    )
    assert answered.status_code == 200
    assert answered.json["status"] == "answered"
    assert app.extensions["klaro"].store.read(token).status == "answered"

    assert client.post(f"/{token}?confirmed=1").status_code == 200


def test_non_post_methods_cannot_confirm(tmp_path, fake_clock: FakeClock) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = create_token(client)
    answer(client, token)

    assert client.put(f"/{token}?confirmed=1").status_code == 405
    assert client.patch(f"/{token}?confirmed=1").status_code == 405
    assert app.extensions["klaro"].store.read(token).status == "answered"


def test_expired_answered_questionnaire_returns_404_not_confirmation(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = create_token(client)
    answer(client, token)
    fake_clock.advance(60)

    response = client.post(f"/{token}?confirmed=1")

    assert response.status_code == 404
    assert response.json["error"]["code"] == "not_found"
    assert app.extensions["klaro"].store.read(token) is None
