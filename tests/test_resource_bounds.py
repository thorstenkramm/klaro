"""Anonymous requests must not accumulate worker memory or monopolize the single worker."""

from __future__ import annotations

import json
import time

import pytest

from klaro import limits, markdown
from tests.app_helpers import make_app, post_creation
from tests.helpers import FakeClock
from tests.test_sse import answer, create_token, next_frame, open_stream


def runtime_state_sizes(app) -> tuple[int, int]:
    runtime = app.extensions["klaro"]
    return len(runtime.store._locks), len(runtime.subscribers._entries)


def test_unknown_and_malformed_tokens_allocate_no_worker_state(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()

    for index in range(200):
        assert client.get(f"/probe{index}").status_code == 404
        assert client.get(f"/{index:043d}").status_code == 404
        assert open_stream(client, f"probe{index}").status_code == 404
        assert open_stream(client, f"{index:043d}").status_code == 404
        assert client.post(f"/probe{index}?confirmed=1").status_code == 404
        assert client.post(f"/{index:043d}", data={"q1": "1"}).status_code == 404

    assert runtime_state_sizes(app) == (0, 0)


def test_lifecycle_releases_locks_and_stream_entries(tmp_path, fake_clock: FakeClock) -> None:
    app, _ = make_app(tmp_path, fake_clock, heartbeat_seconds=60)
    client = app.test_client()
    token = create_token(client)

    stream = open_stream(client, token)
    frames = iter(stream.response)
    next_frame(frames)
    next_frame(frames)
    assert runtime_state_sizes(app) == (0, 1)

    answer(client, token)
    assert next_frame(frames).startswith("event: answer")
    stream.close()
    assert client.post(f"/{token}?confirmed=1").status_code == 200

    assert runtime_state_sizes(app) == (0, 0)


def test_transition_without_listeners_allocates_no_stream_entry(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = create_token(client)

    answer(client, token)
    fake_clock.advance(120)
    app.extensions["klaro"].store.cleanup_expired()

    assert runtime_state_sizes(app) == (0, 0)


@pytest.mark.parametrize("unit", ["[", "![", "[](", "<", "<a>", "\\[", "*_"])
def test_worst_case_questionnaire_page_stays_within_cpu_budget(
    tmp_path, fake_clock: FakeClock, unit: str
) -> None:
    for function in (markdown.render_option, markdown.render_name, markdown.plain_name):
        function.cache_clear()
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    name = "Q " + unit * ((limits.MAX_NAME_CHARACTERS - 2) // len(unit))
    option_body = unit * ((limits.MAX_OPTION_CHARACTERS - 20) // len(unit))
    options = [f"x{index} {option_body}" for index in range(limits.MAX_OPTIONS)]
    # Use as many maximal options as fit into one creation body.
    while len(json.dumps({"questions": [{"name": name, "answers": options}]})) > (
        limits.MAX_BODY_BYTES - 200
    ):
        options.pop()
    body = {"questions": [{"name": name, "type": "checkbox", "answers": options}]}
    created = post_creation(client, body=body)
    assert created.status_code == 201
    path = "/" + created.json["url"].rsplit("/", 1)[1]

    started = time.perf_counter()
    first = client.get(path)
    first_view = time.perf_counter() - started
    started = time.perf_counter()
    client.get(path)
    repeated_view = time.perf_counter() - started

    assert first.status_code == 200
    # Quadratic matching needed about 2.4 s for the "[" page; linear rendering
    # needs about 0.1-0.4 s, and cached repeats need a few milliseconds.
    assert first_view < 1.5
    assert repeated_view < 0.25
