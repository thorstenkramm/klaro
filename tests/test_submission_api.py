from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.app_helpers import make_app, post_creation
from tests.helpers import FakeClock
from tests.response_helpers import selected_by_id


def create_token(client) -> str:
    return post_creation(client).json["url"].rsplit("/", 1)[-1]


@pytest.mark.parametrize(
    ("submission", "field_id"),
    [
        ({}, "q1-error"),
        ({"q1": "1"}, "q2-error"),
        ({"q2": "1"}, "q1-error"),
        ({"q1": ["1", "2"], "q2": "1"}, "q1-error"),
        ({"q1": "wine", "q2": "1"}, "q1-error"),
        ({"q1": "1", "q2": "chips"}, "q2-error"),
        ({"q1": "1", "q2": ["1", "1"]}, "q2-error"),
    ],
)
def test_invalid_submissions_return_422_and_preserve_active_state(
    tmp_path, fake_clock: FakeClock, submission: dict, field_id: str
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = create_token(client)

    response = client.post(f"/{token}", data=submission)
    record = app.extensions["klaro"].store.read(token)

    assert response.status_code == 422
    assert f'id="{field_id}"' in response.text
    assert record.status == "awaiting_answer"
    assert record.answers is None


def test_unknown_question_id_is_rejected_without_closing_answers(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = create_token(client)

    response = client.post(f"/{token}", data={"q1": "1", "q2": "1", "q99": "forged"})
    record = app.extensions["klaro"].store.read(token)

    assert response.status_code == 422
    assert record.status == "awaiting_answer"
    assert record.answers is None


def test_valid_htmx_submission_persists_arrays_and_returns_read_only_fragment(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = create_token(client)

    response = client.post(
        f"/{token}",
        data={"q1": "1", "q2": ["1", "2"]},
        headers={"HX-Request": "true"},
    )
    record = app.extensions["klaro"].store.read(token)

    assert response.status_code == 200
    assert response.text.startswith('<section id="questionnaire-response"')
    assert "<html" not in response.text
    assert "Answer stored" in response.text
    assert "form" not in response.text
    assert record.status == "answered"
    assert selected_by_id(record) == {"q1": ["beer"], "q2": ["rice", "salad"]}


def test_duplicate_submission_is_409_and_preserves_original_answers(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = create_token(client)
    assert client.post(f"/{token}", data={"q1": "1", "q2": "1"}).status_code == 200

    duplicate = client.post(f"/{token}", data={"q1": "2", "q2": "2"})
    record = app.extensions["klaro"].store.read(token)

    assert duplicate.status_code == 409
    assert duplicate.json["error"]["code"] == "state_conflict"
    assert selected_by_id(record) == {"q1": ["beer"], "q2": ["rice"]}


def test_concurrent_submissions_have_exactly_one_winner(tmp_path, fake_clock: FakeClock) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    token = create_token(app.test_client())
    barrier = threading.Barrier(2)

    def submit(choice: str):
        client = app.test_client()
        barrier.wait()
        response = client.post(f"/{token}", data={"q1": choice, "q2": [choice]})
        return response.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(submit, ["1", "2"]))

    assert sorted(statuses) == [200, 409]
    record = app.extensions["klaro"].store.read(token)
    assert record.status == "answered"
    assert selected_by_id(record) in (
        {"q1": ["beer"], "q2": ["rice"]},
        {"q1": ["water"], "q2": ["salad"]},
    )
    stored = json.loads((app.extensions["klaro"].store.directory / f"{token}.json").read_text())
    assert stored["answers"] == {
        key: {"answered": values, "other": None, "comment": None}
        for key, values in selected_by_id(record).items()
    }
