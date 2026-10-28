from __future__ import annotations

import json

import pytest

from tests.app_helpers import IP, QUESTIONER, RECIPIENT, make_app, post_creation
from tests.helpers import FakeClock
from tests.test_sse import decode_frame, next_frame

REC_BODY = {
    "questions": [
        {
            "name": "Drink?",
            "type": "radio",
            "answers": ["beer", "water", "wine", "tea"],
            "allow_other": True,
            "allow_comments": True,
            "recommendations": [4, 1],
        },
        {
            "name": "Sides?",
            "type": "checkbox",
            "answers": ["rice", "salad"],
            "recommendations": [2],
        },
    ]
}


def recommendation_token(client) -> str:
    response = post_creation(client, body=REC_BODY)
    assert response.status_code == 201
    return response.json["url"].rsplit("/", 1)[-1]


@pytest.mark.parametrize("content_type", ["application/json", "application/yaml"])
def test_recommendations_normalize_in_json_and_yaml(
    tmp_path, fake_clock: FakeClock, content_type: str
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    if content_type == "application/json":
        response = post_creation(app.test_client(), body=REC_BODY)
    else:
        response = app.test_client().post(
            "/",
            data=(
                "questions:\n"
                "  - name: Drink?\n"
                "    type: radio\n"
                "    answers: [beer, water, wine, tea]\n"
                "    recommendations: [4, 1]\n"
            ),
            content_type=content_type,
            headers={"X-Pushover-User": RECIPIENT, "X-Questioner": QUESTIONER},
            environ_base={"REMOTE_ADDR": IP},
        )
    assert response.status_code == 201
    token = response.json["url"].rsplit("/", 1)[-1]
    record = app.extensions["klaro"].store.read(token)
    assert record.questions[0].recommendations == (1, 4)
    assert record.questions[0].as_dict()["recommendations"] == [1, 4]
    assert record.public_dict()["questions"][0]["recommendations"] == [1, 4]


@pytest.mark.parametrize(
    "recommendations",
    [
        None,
        1,
        "1",
        True,
        1.0,
        [True],
        [False],
        ["1"],
        [1.0],
        [0],
        [-1],
        [5],
        [1, 1],
        ["other"],
        [1, "other"],
        [[]],
    ],
)
def test_invalid_recommendations_have_exact_field_and_no_side_effects(
    tmp_path, fake_clock: FakeClock, recommendations
) -> None:
    app, transport = make_app(tmp_path, fake_clock)
    body = json.loads(json.dumps(REC_BODY))
    body["questions"][0]["recommendations"] = recommendations
    response = post_creation(app.test_client(), body=body)
    assert response.status_code == 400
    assert response.json["error"]["code"] == "invalid_request"
    assert set(response.json["error"]["fields"]) == {"questions.0.recommendations"}
    assert transport.call_count == 0
    assert list(app.extensions["klaro"].store.directory.iterdir()) == []


@pytest.mark.parametrize("value", ["true", "[true]", "[1.0]", "['1']", "[1, 1]", "[3]"])
def test_yaml_rejects_noninteger_out_of_range_and_duplicate_recommendations(
    tmp_path, fake_clock: FakeClock, value: str
) -> None:
    app, transport = make_app(tmp_path, fake_clock)
    response = app.test_client().post(
        "/",
        data=(
            "questions:\n"
            "  - name: Drink?\n"
            "    type: radio\n"
            "    answers: [beer, water]\n"
            f"    recommendations: {value}\n"
        ),
        content_type="application/yaml",
        headers={"X-Pushover-User": RECIPIENT, "X-Questioner": QUESTIONER},
        environ_base={"REMOTE_ADDR": IP},
    )
    assert response.status_code == 400
    assert set(response.json["error"]["fields"]) == {"questions.0.recommendations"}
    assert transport.call_count == 0
    assert list(app.extensions["klaro"].store.directory.iterdir()) == []


def test_asterisks_and_backslashes_are_literal_not_recommendations(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    body = {
        "questions": [
            {
                "name": "Literal?",
                "type": "checkbox",
                "answers": ["*wine", "\\*wine"],
            }
        ]
    }
    token = post_creation(app.test_client(), body=body).json["url"].rsplit("/", 1)[-1]
    before = app.test_client().get(f"/{token}?answer_only=1").json
    assert before["questions"][0]["recommendations"] == []
    assert app.test_client().post(f"/{token}", data={"q1": ["1", "2"]}).status_code == 200
    after = app.test_client().get(f"/{token}?answer_only=1").json
    assert after["questions"][0]["answered"] == ["*wine", "\\*wine"]
    assert after["questions"][0]["recommendations"] == []


def test_recommendations_match_full_polling_sse_and_restart(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, _ = make_app(tmp_path, fake_clock, heartbeat_seconds=60)
    client = app.test_client()
    token = recommendation_token(client)
    full_before = client.get(f"/{token}", headers={"Accept": "application/json"}).json
    poll_before = client.get(f"/{token}?answer_only=1").json
    assert full_before["answered_at"] is None
    assert full_before["questions"][0]["recommendations"] == [1, 4]
    assert full_before["questions"][1]["recommendations"] == [2]
    assert poll_before["questions"][0]["recommendations"] == [1, 4]
    assert set(full_before["questions"][0]) == {
        "name",
        "type",
        "answers",
        "allow_other",
        "allow_comments",
        "answered",
        "other",
        "comment",
        "recommendations",
    }
    assert set(poll_before["questions"][0]) == {
        "name",
        "answered",
        "other",
        "comment",
        "recommendations",
    }

    stream_response = client.get(
        f"/{token}", headers={"Accept": "text/event-stream"}, buffered=False
    )
    stream = iter(stream_response.response)
    assert next_frame(stream) == "retry: 5000\n\n"
    event, _ = decode_frame(next_frame(stream))
    assert event == "status"
    assert (
        client.post(
            f"/{token}",
            data={"q1": "other", "q1-other": "custom", "q1-comment": "note", "q2": "1"},
        ).status_code
        == 200
    )
    event, streamed = decode_frame(next_frame(stream))
    assert event == "answer"
    assert list(stream) == []
    stream_response.close()
    assert streamed["questions"][0]["recommendations"] == [1, 4]
    assert streamed["questions"][0]["answered"] == []
    assert streamed["questions"][0]["other"] == "custom"

    full_after = client.get(f"/{token}", headers={"Accept": "application/json"}).json
    poll_after = client.get(f"/{token}?answer_only=1").json
    assert poll_after == streamed
    assert full_after["answered_at"] == "2026-10-25T12:00:00Z"
    assert full_after["expires_at"] == "2026-10-25T12:01:00Z"
    assert [q["recommendations"] for q in full_after["questions"]] == [[1, 4], [2]]
    restarted, _ = make_app(tmp_path, fake_clock)
    assert restarted.test_client().get(f"/{token}?answer_only=1").json == streamed
