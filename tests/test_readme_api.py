from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.app_helpers import IP, RECIPIENT, make_app
from tests.helpers import FakeClock

README = (Path(__file__).parent.parent / "README.md").read_text()


def example(name: str, language: str) -> str:
    match = re.search(
        rf"<!-- example:{re.escape(name)} -->\s*(?P<fence>`{{3,}}){language}\n"
        rf"(?P<body>.*?)(?P=fence)",
        README,
        re.DOTALL,
    )
    assert match is not None, f"Missing README example {name}"
    return match.group("body").strip()


def here_document(script: str, marker: str) -> str:
    return script.split(f"<<'{marker}'\n", 1)[1].rsplit(f"\n{marker}", 1)[0]


def create(client, body: str, content_type: str):
    return client.post(
        "/",
        data=body,
        content_type=content_type,
        headers={"X-Pushover-User": RECIPIENT, "X-Questioner": "Your dinner mate"},
        environ_base={"REMOTE_ADDR": IP},
    )


def answer(client, token: str) -> None:
    response = client.post(f"/{token}", data={"q1": "1", "q2": ["1", "2"]})
    assert response.status_code == 200


def next_text(stream) -> str:
    value = next(stream)
    return value.decode() if isinstance(value, bytes) else value


def event_data(frame: str) -> tuple[str, dict]:
    lines = frame.splitlines()
    event = lines[0].removeprefix("event: ")
    data = "\n".join(line.removeprefix("data: ") for line in lines[1:] if line)
    return event, json.loads(data)


def expected_creation(token: str) -> dict:
    return json.loads(example("creation-response", "json").replace("<token>", token))


def test_readme_json_creation_retrieval_polling_and_confirmation_examples(
    tmp_path, fake_clock: FakeClock
) -> None:
    script = example("json-create", "shell")
    assert "Content-Type: application/json" in script
    body = here_document(script, "JSON")
    app, transport = make_app(tmp_path, fake_clock)
    client = app.test_client()

    created = create(client, body, "application/json")
    assert created.status_code == 201
    assert transport.call_count == 1
    token = created.json["url"].rsplit("/", 1)[-1]
    assert created.json == expected_creation(token)

    retrieve_script = example("retrieve", "shell")
    assert "Accept: application/json" in retrieve_script
    retrieved = client.get(f"/{token}", headers={"Accept": "application/json"})
    assert retrieved.status_code == 200
    assert retrieved.json == json.loads(example("retrieval-response", "json"))

    answer(client, token)
    polling_script = example("answer-only", "shell")
    assert "$URL?answer_only=1" in polling_script
    polled = client.get(f"/{token}?answer_only=1")
    assert polled.json == json.loads(example("answer-only-response", "json"))

    confirmation_script = example("confirm", "shell")
    assert "-X POST" in confirmation_script
    assert "$URL?confirmed=1" in confirmation_script
    confirmed = client.post(f"/{token}?confirmed=1")
    assert confirmed.status_code == 200
    assert confirmed.json == json.loads(example("confirmation-response", "json"))
    assert client.get(f"/{token}").status_code == 404


def test_readme_yaml_example_creates_the_same_documented_questionnaire(
    tmp_path, fake_clock: FakeClock
) -> None:
    script = example("yaml-create", "shell")
    assert "Content-Type: application/yaml" in script
    body = here_document(script, "YAML")
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()

    created = create(client, body, "application/yaml")
    assert created.status_code == 201
    token = created.json["url"].rsplit("/", 1)[-1]
    assert created.json == expected_creation(token)
    retrieved = client.get(f"/{token}", headers={"Accept": "application/json"})
    assert retrieved.json == json.loads(example("retrieval-response", "json"))


def test_readme_sse_example_matches_streamed_answer_and_closes(
    tmp_path, fake_clock: FakeClock
) -> None:
    javascript = example("sse-client", "javascript")
    assert "new EventSource(URL)" in javascript
    for event in ["status", "heartbeat", "answer", "expired"]:
        assert f'addEventListener("{event}"' in javascript
    assert javascript.count("source.close()") == 2
    assert 'curl -N -H "Accept: text/event-stream" "$URL"' in README

    app, _ = make_app(tmp_path, fake_clock, heartbeat_seconds=60)
    client = app.test_client()
    created = create(
        client,
        example("json-create", "shell").split("<<'JSON'\n")[1].rsplit("\nJSON", 1)[0],
        "application/json",
    )
    token = created.json["url"].rsplit("/", 1)[-1]
    response = client.get(f"/{token}", headers={"Accept": "text/event-stream"}, buffered=False)
    stream = iter(response.response)

    assert next_text(stream) == "retry: 5000\n\n"
    assert event_data(next_text(stream))[0] == "status"
    answer(client, token)
    event, data = event_data(next_text(stream))
    assert event == "answer"
    assert data == json.loads(example("sse-answer", "json"))
    with pytest.raises(StopIteration):
        next(stream)


def test_obsolete_readme_contract_is_removed() -> None:
    assert "confirm_reception" not in README
    assert "To confirm reception fetch" not in README
    assert "Content-Type`-based" not in README
