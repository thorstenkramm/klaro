from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from klaro.answers import SubmittedAnswer
from tests.app_helpers import IP, QUESTIONER, RECIPIENT, make_app, post_creation
from tests.helpers import FakeClock
from tests.response_helpers import selected_by_id
from tests.test_sse import decode_frame, next_frame

RICH_BODY = {
    "questions": [
        {
            "name": "Drink?",
            "type": "radio",
            "answers": ["beer", "water"],
            "allow_other": True,
            "allow_comments": True,
        },
        {
            "name": "Sides?",
            "type": "checkbox",
            "answers": ["rice", "salad"],
            "allow_other": True,
        },
    ]
}


def rich_token(client) -> str:
    response = post_creation(client, body=RICH_BODY)
    assert response.status_code == 201
    return response.json["url"].rsplit("/", 1)[-1]


@pytest.mark.parametrize("content_type", ["application/json", "application/yaml"])
def test_creation_accepts_strict_text_opt_ins(
    tmp_path, fake_clock: FakeClock, content_type: str
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    if content_type == "application/json":
        response = post_creation(app.test_client(), body=RICH_BODY)
    else:
        response = app.test_client().post(
            "/",
            data=(
                "questions:\n"
                "  - name: Drink?\n"
                "    type: radio\n"
                "    answers: [beer, water]\n"
                "    allow_other: true\n"
                "    allow_comments: true\n"
            ),
            content_type=content_type,
            headers={"X-Pushover-User": RECIPIENT, "X-Questioner": QUESTIONER},
            environ_base={"REMOTE_ADDR": IP},
        )
    assert response.status_code == 201
    token = response.json["url"].rsplit("/", 1)[-1]
    record = app.extensions["klaro"].store.read(token)
    assert record.questions[0].allow_other is True
    assert record.questions[0].allow_comments is True
    assert record.questions[0].as_dict()["allow_other"] is True


@pytest.mark.parametrize("flag", ["allow_other", "allow_comments"])
def test_invalid_text_opt_in_has_no_creation_side_effects(
    tmp_path, fake_clock: FakeClock, flag: str
) -> None:
    app, transport = make_app(tmp_path, fake_clock)
    body = json.loads(json.dumps(RICH_BODY))
    body["questions"][0][flag] = "true"
    response = post_creation(app.test_client(), body=body)
    assert response.status_code == 400
    assert response.json["error"]["fields"] == {f"questions.0.{flag}": ["Must be a boolean."]}
    assert transport.call_count == 0
    assert list(app.extensions["klaro"].store.directory.iterdir()) == []


def test_structured_storage_level_answers_keep_text_separate(tmp_path, fake_clock) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    token = rich_token(app.test_client())
    store = app.extensions["klaro"].store
    result = store.submit_answers(
        token,
        {
            "q1": SubmittedAnswer((), "sparkling water", "no ice"),
            "q2": SubmittedAnswer(("rice",), "corn"),
        },
    )
    assert selected_by_id(result) == {"q1": [], "q2": ["rice"]}
    assert result.answers["q1"].other == "sparkling water"
    assert result.answers["q1"].comment == "no ice"


def test_rich_answers_are_consistent_across_full_polling_and_sse(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, _ = make_app(tmp_path, fake_clock, heartbeat_seconds=60)
    client = app.test_client()
    token = rich_token(client)
    before = client.get(f"/{token}", headers={"Accept": "application/json"}).json
    assert before["questions"][0] == {
        "name": "Drink?",
        "type": "radio",
        "answers": ["beer", "water"],
        "allow_other": True,
        "allow_comments": True,
        "answered": None,
        "other": None,
        "comment": None,
        "recommendations": [],
    }
    submitted = client.post(
        f"/{token}",
        data={
            "q1": "other",
            "q1-other": " sparkling water ",
            "q1-comment": " no ice ",
            "q2": ["1", "other"],
            "q2-other": " grilled corn ",
        },
    )
    assert submitted.status_code == 200
    full = client.get(f"/{token}", headers={"Accept": "application/json"})
    assert full.status_code == 200
    assert full.json["expires_at"] == "2026-10-25T12:01:00Z"
    assert full.json["answered_at"] == "2026-10-25T12:00:00Z"
    assert full.json["questions"][0]["answered"] == []
    assert full.json["questions"][0]["other"] == "sparkling water"
    assert full.json["questions"][0]["comment"] == "no ice"
    assert full.json["questions"][1]["answered"] == ["rice"]
    assert full.json["questions"][1]["other"] == "grilled corn"
    assert full.json["questions"][1]["comment"] is None
    poll = client.get(f"/{token}?answer_only=1").json
    assert set(poll) == {"answered_at", "questions"}
    assert all(
        set(question) == {"name", "answered", "other", "comment", "recommendations"}
        for question in poll["questions"]
    )
    assert poll["questions"] == [
        {
            key: value
            for key, value in question.items()
            if key not in {"type", "answers", "allow_other", "allow_comments"}
        }
        for question in full.json["questions"]
    ]
    stream_response = client.get(
        f"/{token}", headers={"Accept": "text/event-stream"}, buffered=False
    )
    stream = iter(stream_response.response)
    assert next_frame(stream) == "retry: 5000\n\n"
    event, answer = decode_frame(next_frame(stream))
    assert event == "answer"
    assert answer == poll
    assert list(stream) == []
    stream_response.close()

    restarted, _ = make_app(tmp_path, fake_clock)
    assert restarted.test_client().get(f"/{token}?answer_only=1").json == poll
    assert (
        app.extensions["klaro"].store.read(token).answered_at.isoformat()
        == "2026-10-25T12:00:00+00:00"
    )


def test_rich_competing_submissions_and_expiry(tmp_path, fake_clock: FakeClock) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = rich_token(client)
    expiring_token = rich_token(client)
    assert client.get(f"/{token}?answer_only=1").json["answered_at"] is None
    barrier = threading.Barrier(2)

    def submit(index: int):
        barrier.wait()
        response = app.test_client().post(
            f"/{token}",
            data={
                "q1": "other",
                "q1-other": f"custom-{index}",
                "q1-comment": f"comment-{index}",
                "q2": str(index + 1),
            },
        )
        return response.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(submit, range(2)))
    assert sorted(statuses) == [200, 409]
    winner = app.extensions["klaro"].store.read(token)
    assert winner.answers["q1"].other in {"custom-0", "custom-1"}
    assert winner.answers["q1"].comment == f"comment-{winner.answers['q1'].other[-1]}"
    assert winner.answered_at.isoformat() == "2026-10-25T12:00:00+00:00"

    fake_clock.advance(60)
    assert app.extensions["klaro"].store.cleanup_expired() == 2
    assert client.get(f"/{token}").status_code == 404
    assert client.get(f"/{expiring_token}").status_code == 404
