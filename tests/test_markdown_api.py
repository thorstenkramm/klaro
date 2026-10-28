from __future__ import annotations

import json

import pytest
import yaml

from tests.app_helpers import IP, QUESTIONER, RECIPIENT, make_app, post_creation
from tests.helpers import FakeClock
from tests.test_readme_api import example
from tests.test_sse import decode_frame, next_frame

MARKDOWN_BODY = {
    "questions": [
        {
            "name": "How should we **clean up** `/your-folder`?",
            "type": "radio",
            "answers": [
                "Delete **recursively**\n```sh\ncd /your-folder\nrm -rf\n```\n",
                'Delete with a *loop*\n\n```sh\nfor file in *.png; do\n  rm "$file"\ndone\n```',
            ],
            "allow_other": True,
            "allow_comments": True,
            "recommendations": [2, 1],
        },
        {
            "name": "Anything else?",
            "type": "checkbox",
            "answers": ["Keep `notes`", "Use [literal](https://example.com)"],
        },
    ]
}


def markdown_token(client) -> str:
    response = post_creation(client, body=MARKDOWN_BODY)
    assert response.status_code == 201
    return response.json["url"].rsplit("/", 1)[-1]


def test_readme_markdown_yaml_is_executable_and_preserves_sources(
    tmp_path, fake_clock: FakeClock
) -> None:
    body = yaml.safe_load(example("markdown-yaml", "yaml"))
    app, _ = make_app(tmp_path, fake_clock)
    response = post_creation(app.test_client(), body=body)
    assert response.status_code == 201
    token = response.json["url"].rsplit("/", 1)[-1]
    record = app.extensions["klaro"].store.read(token)
    assert record.questions[0].answers == tuple(body["questions"][0]["answers"])
    assert record.questions[0].answers[0].startswith("Delete recursively\n```")


@pytest.mark.parametrize(
    "option",
    ["```\ncode\n```", "\n\n```python\ncode\n```", "    indented code", "~~~\ncode\n~~~"],
)
def test_code_first_options_are_400_with_exact_field_and_no_side_effects(
    tmp_path, fake_clock: FakeClock, option: str
) -> None:
    app, transport = make_app(tmp_path, fake_clock)
    body = json.loads(json.dumps(MARKDOWN_BODY))
    body["questions"][0]["answers"][0] = option
    response = post_creation(app.test_client(), body=body)
    assert response.status_code == 400
    assert response.json["error"]["fields"] == {
        "questions.0.answers.0": ["Must begin with a nonempty paragraph before any code block."]
    }
    assert transport.call_count == 0
    assert list(app.extensions["klaro"].store.directory.iterdir()) == []


def test_leading_blank_lines_and_inline_code_heads_are_accepted(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    body = json.loads(json.dumps(MARKDOWN_BODY))
    body["questions"][0]["answers"][0] = "\n\n`inline` **head**\n\n    code body"
    token = post_creation(app.test_client(), body=body).json["url"].rsplit("/", 1)[-1]
    record = app.extensions["klaro"].store.read(token)
    assert record.questions[0].answers[0] == body["questions"][0]["answers"][0]


@pytest.mark.parametrize(("length", "status"), [(2_000, 201), (2_001, 400)])
def test_markdown_option_source_boundaries(
    tmp_path, fake_clock: FakeClock, length: int, status: int
) -> None:
    app, transport = make_app(tmp_path, fake_clock)
    body = json.loads(json.dumps(MARKDOWN_BODY))
    body["questions"][0]["answers"][0] = "x" * length
    response = post_creation(app.test_client(), body=body)
    assert response.status_code == status
    if status == 400:
        assert set(response.json["error"]["fields"]) == {"questions.0.answers.0"}
        assert transport.call_count == 0


def test_individually_valid_markdown_options_retain_creation_byte_cap(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, transport = make_app(tmp_path, fake_clock)
    body = {
        "questions": [
            {
                "name": "Large",
                "type": "checkbox",
                "answers": [f"{index}:{'x' * 1_997}" for index in range(50)],
            }
        ]
    }
    response = post_creation(app.test_client(), body=body)
    assert response.status_code == 413
    assert response.json["error"]["code"] == "payload_too_large"
    assert transport.call_count == 0
    assert list(app.extensions["klaro"].store.directory.iterdir()) == []


def test_formatted_names_retain_exact_uniqueness_rules(tmp_path, fake_clock: FakeClock) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    distinct = {
        "questions": [
            {"name": "**Same**", "type": "radio", "answers": ["one", "two"]},
            {"name": "Same", "type": "radio", "answers": ["one", "two"]},
        ]
    }
    assert post_creation(app.test_client(), body=distinct).status_code == 201


def test_markdown_source_fidelity_json_sse_restart_and_confirmation(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, _ = make_app(tmp_path, fake_clock, heartbeat_seconds=60)
    client = app.test_client()
    created = post_creation(client, body=MARKDOWN_BODY, headers={"Accept": "text/event-stream"})
    assert created.status_code == 303
    assert created.data == b""
    token = created.headers["Location"].lstrip("/")
    source = MARKDOWN_BODY["questions"][0]["answers"][0]
    assert source.endswith("\n")
    stored_path = app.extensions["klaro"].store.directory / f"{token}.json"
    stored = json.loads(stored_path.read_text())
    assert stored["version"] == 4
    assert stored["questions"][0]["answers"] == MARKDOWN_BODY["questions"][0]["answers"]
    assert stored["questions"][0]["recommendations"] == [1, 2]

    full_before = client.get(f"/{token}", headers={"Accept": "application/json"}).json
    assert full_before["questions"][0]["answers"] == MARKDOWN_BODY["questions"][0]["answers"]
    assert full_before["questions"][0]["recommendations"] == [1, 2]
    stream_response = client.get(
        created.headers["Location"], headers={"Accept": "text/event-stream"}, buffered=False
    )
    stream = iter(stream_response.response)
    assert next_frame(stream) == "retry: 5000\n\n"
    event, _ = decode_frame(next_frame(stream))
    assert event == "status"
    submitted = client.post(
        f"/{token}", data={"q1": "1", "q1-comment": "**literal comment**", "q2": "2"}
    )
    assert submitted.status_code == 200
    event, answer = decode_frame(next_frame(stream))
    assert event == "answer"
    assert list(stream) == []
    stream_response.close()
    assert answer["answered_at"] == "2026-10-25T12:00:00Z"
    assert answer["questions"][0]["answered"] == [source]
    assert answer["questions"][0]["comment"] == "**literal comment**"
    assert answer["questions"][0]["recommendations"] == [1, 2]
    assert answer["questions"][1]["answered"] == [MARKDOWN_BODY["questions"][1]["answers"][1]]

    first_poll = client.get(f"/{token}?answer_only=1").json
    second_poll = client.get(f"/{token}?answer_only=1").json
    assert first_poll == second_poll == answer
    full_after = client.get(f"/{token}", headers={"Accept": "application/json"}).json
    assert full_after["expires_at"] == "2026-10-25T12:01:00Z"
    assert full_after["answered_at"] == answer["answered_at"]
    assert full_after["questions"][0]["answers"] == MARKDOWN_BODY["questions"][0]["answers"]
    assert "<strong>" not in json.dumps(full_after)
    stored_answered = json.loads(stored_path.read_text())
    assert stored_answered["answers"]["q1"]["answered"] == [source]
    assert stored_answered["answers"]["q1"]["comment"] == "**literal comment**"

    restarted, _ = make_app(tmp_path, fake_clock)
    restarted_client = restarted.test_client()
    assert restarted_client.get(f"/{token}?answer_only=1").json == answer
    assert (
        restarted_client.get(f"/{token}", headers={"Accept": "application/json"}).json == full_after
    )
    assert restarted_client.post(f"/{token}?confirmed=1").status_code == 200
    assert restarted.extensions["klaro"].store.read(token) is None


def test_combined_yaml_polling_all_feedback_features(tmp_path, fake_clock: FakeClock) -> None:
    body = yaml.safe_load(example("markdown-yaml", "yaml"))
    body["questions"][0]["allow_other"] = True
    body["questions"][0]["allow_comments"] = True
    body["questions"].append(
        {
            "name": "Choose **sides**",
            "type": "checkbox",
            "answers": ["rice", "salad `cold`"],
            "allow_other": True,
            "allow_comments": True,
            "recommendations": [2],
        }
    )
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    created = client.post(
        "/",
        data=yaml.safe_dump(body, sort_keys=False, allow_unicode=True),
        content_type="application/yaml",
        headers={"X-Pushover-User": RECIPIENT, "X-Questioner": QUESTIONER},
        environ_base={"REMOTE_ADDR": IP},
    )
    assert created.status_code == 201
    token = created.json["url"].rsplit("/", 1)[-1]
    before = client.get(f"/{token}?answer_only=1").json
    assert before["answered_at"] is None
    assert [question["recommendations"] for question in before["questions"]] == [[2], [2]]
    submitted = client.post(
        f"/{token}",
        data={
            "q1": "other",
            "q1-other": " **custom** ",
            "q1-comment": " `literal` ",
            "q2": ["2", "other"],
            "q2-other": " corn ",
            "q2-comment": " **dairy-free** ",
        },
    )
    assert submitted.status_code == 200
    answer = client.get(f"/{token}?answer_only=1").json
    assert answer["answered_at"] == "2026-10-25T12:00:00Z"
    assert answer["questions"][0]["answered"] == []
    assert answer["questions"][0]["other"] == "**custom**"
    assert answer["questions"][0]["comment"] == "`literal`"
    assert answer["questions"][1]["answered"] == ["salad `cold`"]
    assert answer["questions"][1]["other"] == "corn"
    assert answer["questions"][1]["comment"] == "**dairy-free**"
    assert [question["recommendations"] for question in answer["questions"]] == [[2], [2]]
    full = client.get(f"/{token}", headers={"Accept": "application/json"}).json
    assert full["questions"][0]["answers"] == body["questions"][0]["answers"]
    assert full["expires_at"] == "2026-10-25T12:01:00Z"

    restarted, _ = make_app(tmp_path, fake_clock)
    restarted_client = restarted.test_client()
    assert restarted_client.get(f"/{token}?answer_only=1").json == answer
    assert restarted_client.get(f"/{token}?answer_only=1").json == answer
    assert restarted_client.post(f"/{token}?confirmed=1").status_code == 200
