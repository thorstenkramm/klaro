from __future__ import annotations

import pytest

from tests.app_helpers import RECIPIENT, make_app, post_creation
from tests.helpers import FakeClock


def create_token(client) -> str:
    response = post_creation(client)
    assert response.status_code == 201
    return response.json["url"].rsplit("/", 1)[-1]


def answer(client, token: str) -> None:
    response = client.post(f"/{token}", data={"q1": "beer", "q2": ["rice", "salad"]})
    assert response.status_code == 200


def test_full_json_before_answering_has_stable_ids_and_null_answers(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = create_token(client)

    first = client.get(f"/{token}", headers={"Accept": "application/json"})
    second = client.get(f"/{token}", headers={"Accept": "application/json"})

    assert first.status_code == second.status_code == 200
    assert first.json == second.json
    assert first.json == {
        "status": "awaiting_answer",
        "expires_at": "2026-10-25T12:01:00Z",
        "questions": [
            {"id": "q1", "name": "Drink?", "type": "radio", "answers": ["beer", "water"]},
            {
                "id": "q2",
                "name": "Sides?",
                "type": "checkbox",
                "answers": ["rice", "salad"],
            },
        ],
        "answers": None,
    }
    assert app.extensions["klaro"].store.read(token).status == "awaiting_answer"


def test_full_json_after_answering_is_complete_and_non_destructive(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = create_token(client)
    answer(client, token)

    first = client.get(f"/{token}", headers={"Accept": "application/json"})
    second = client.get(f"/{token}", headers={"Accept": "application/json"})

    assert first.status_code == second.status_code == 200
    assert first.json == second.json
    assert first.json["status"] == "answered"
    assert first.json["answers"] == {"q1": ["beer"], "q2": ["rice", "salad"]}
    assert len(first.json["questions"]) == 2
    assert app.extensions["klaro"].store.read(token).status == "answered"


def test_answer_only_before_and_after_submission_is_repeatable(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = create_token(client)

    before = client.get(f"/{token}?answer_only=1")
    before_again = client.get(f"/{token}?answer_only=1")
    answer(client, token)
    after = client.get(f"/{token}?answer_only=1")
    after_again = client.get(f"/{token}?answer_only=1")

    assert (
        before.json
        == before_again.json
        == {
            "status": "awaiting_answer",
            "answers": None,
        }
    )
    assert (
        after.json
        == after_again.json
        == {
            "status": "answered",
            "answers": {"q1": ["beer"], "q2": ["rice", "salad"]},
        }
    )
    for response in [before, before_again, after, after_again]:
        assert set(response.json) == {"status", "answers"}
        assert response.mimetype == "application/json"
    assert app.extensions["klaro"].store.read(token) is not None


@pytest.mark.parametrize(
    "accept,expected_mimetype",
    [
        ("application/json", "application/json"),
        ("application/json, text/html;q=0.5", "application/json"),
        ("text/html", "text/html"),
        ("text/html, application/json;q=0.9", "text/html"),
        ("*/*", "text/html"),
        (None, "text/html"),
    ],
)
def test_accept_selects_json_or_html(
    tmp_path, fake_clock: FakeClock, accept: str | None, expected_mimetype: str
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = create_token(client)
    headers = {} if accept is None else {"Accept": accept}

    response = client.get(f"/{token}", headers=headers)

    assert response.status_code == 200
    assert response.mimetype == expected_mimetype


def test_answer_only_overrides_html_negotiation(tmp_path, fake_clock: FakeClock) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = create_token(client)

    response = client.get(f"/{token}?answer_only=1", headers={"Accept": "text/html"})

    assert response.mimetype == "application/json"
    assert set(response.json) == {"status", "answers"}


def test_pending_token_has_same_generic_404_as_unknown(tmp_path, fake_clock: FakeClock) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    runtime = app.extensions["klaro"]
    pending = runtime.store.create_pending(
        questions=[], questioner="Dinner mate", lifetime_seconds=60
    )

    pending_response = app.test_client().get(f"/{pending.token}")
    unknown_response = app.test_client().get("/" + "x" * 43)

    assert pending_response.status_code == unknown_response.status_code == 404
    assert pending_response.get_data() == unknown_response.get_data()
    assert pending_response.json == {
        "error": {"code": "not_found", "message": "Questionnaire not found."}
    }


def test_unknown_expired_and_confirmed_tokens_have_identical_404(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    expired_token = create_token(client)
    fake_clock.advance(60)
    expired = client.get(f"/{expired_token}")

    # Use a fresh clock/app for a confirmed token so it is not expired too.
    confirmed_app, _ = make_app(tmp_path / "confirmed", FakeClock())
    confirmed_client = confirmed_app.test_client()
    confirmed_token = create_token(confirmed_client)
    answer(confirmed_client, confirmed_token)
    assert confirmed_client.post(f"/{confirmed_token}?confirmed=1").status_code == 200
    confirmed = confirmed_client.get(f"/{confirmed_token}")
    unknown = client.get("/" + "z" * 43)

    assert expired.status_code == confirmed.status_code == unknown.status_code == 404
    assert expired.get_data() == confirmed.get_data() == unknown.get_data()


def test_retrieval_does_not_leak_capability_token_or_recipient(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = create_token(client)

    for response in [
        client.get(f"/{token}", headers={"Accept": "application/json"}),
        client.get(f"/{token}?answer_only=1"),
    ]:
        body = response.get_data(as_text=True)
        assert token not in body
        assert RECIPIENT not in body
        assert "a" * 30 not in body
