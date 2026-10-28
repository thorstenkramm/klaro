from __future__ import annotations

import json
import os
import select
import signal
import subprocess
import time

import requests
from flask import request

from klaro.answers import SubmittedAnswer
from tests.app_helpers import RECIPIENT, make_app
from tests.browser_helpers import running_server
from tests.helpers import FakeClock
from tests.test_readme_api import example


def curl_command(
    base_url: str, invalid: bool = False, rich: bool = False, recommendations: bool = False
) -> str:
    script = example("create-and-wait", "shell")
    assert "-L" in script
    assert "-N" in script
    assert "--fail-with-body" in script
    assert "--post303" not in script
    assert "-X POST" not in script
    assert "%{url_effective}" in script
    script = script.replace("https://klaro.example.com/", base_url)
    script = script.replace("<your-key>", RECIPIENT)
    if invalid:
        script = script.replace(
            "questions:\n  - name: Drink?\n    type: radio\n    answers: [beer, water]"
            "\n  - name: Sides?\n    type: checkbox\n    answers: [rice, salad]",
            "questions: []",
        )
    if recommendations:
        script = script.replace(
            "answers: [beer, water]", "answers: [beer, water]\n    recommendations: [2, 1]"
        )
        script = script.replace(
            "answers: [rice, salad]", "answers: [rice, salad]\n    recommendations: [2]"
        )
    if rich:
        script = script.replace(
            "answers: [beer, water]",
            "answers: [beer, water]\n    allow_other: true\n    allow_comments: true",
        )
        script = script.replace(
            "answers: [rice, salad]",
            "answers: [rice, salad]\n    allow_other: true\n    allow_comments: true",
        )
    return script


def start_curl(
    base_url: str, invalid: bool = False, rich: bool = False, recommendations: bool = False
) -> subprocess.Popen:
    return subprocess.Popen(
        ["/bin/bash", "-c", curl_command(base_url, invalid, rich, recommendations)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
        start_new_session=True,
    )


def wait_for_status(process: subprocess.Popen) -> str:
    output = b""
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        ready, _, _ = select.select([process.stdout], [], [], 0.1)
        if not ready:
            assert process.poll() is None, process.stderr.read()
        else:
            output += os.read(process.stdout.fileno(), 4096)
            if b"event: status" in output:
                return output.decode()
    raise AssertionError("curl did not receive an SSE status event")


def test_readme_curl_creates_waits_and_does_not_automatically_confirm(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, transport = make_app(tmp_path, fake_clock, heartbeat_seconds=60)
    seen = []

    @app.before_request
    def capture_request() -> None:
        seen.append((request.method, request.path, request.get_data()))

    with running_server(app) as base_url:
        process = start_curl(base_url)
        try:
            initial = wait_for_status(process)
            assert "retry: 5000" in initial
            token = seen[1][1].lstrip("/")
            assert (
                app.test_client().post(f"/{token}", data={"q1": "1", "q2": ["1", "2"]}).status_code
                == 200
            )
            stdout, stderr = process.communicate(timeout=10)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate(timeout=5)

    stdout = stdout.decode()
    stderr = stderr.decode()
    assert process.returncode == 0
    assert "event: answer" in stdout
    assert "event: expired" not in stdout
    assert (
        json.loads(next(line[6:] for line in initial.splitlines() if line.startswith("data: ")))[
            "answered_at"
        ]
        is None
    )
    assert f"URL: {base_url}/{token}" in stderr
    assert seen[0][0] == "POST"
    assert seen[1] == ("GET", f"/{token}", b"")
    assert app.extensions["klaro"].store.read(token).status == "answered"
    assert transport.call_count == 1


def test_readme_curl_fast_answer_uses_effective_url_for_confirmation(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, transport = make_app(tmp_path, fake_clock, heartbeat_seconds=60)
    token = "0" * 43

    @app.after_request
    def answer_before_redirect_returns(response):
        if request.method == "POST" and request.path == "/" and response.status_code == 303:
            app.extensions["klaro"].store.submit_answers(
                token, {"q1": SubmittedAnswer(("beer",)), "q2": SubmittedAnswer(("rice", "salad"))}
            )
        return response

    with running_server(app) as base_url:
        process = start_curl(base_url)
        stdout, stderr = (part.decode() for part in process.communicate(timeout=10))
        assert process.returncode == 0
        assert "event: status" not in stdout
        assert "event: answer" in stdout
        effective_url = next(line[5:] for line in stderr.splitlines() if line.startswith("URL: "))
        assert effective_url == f"{base_url}/{token}"
        confirmed = requests.post(effective_url + "?confirmed=1", timeout=5)
        assert confirmed.status_code == 200
        assert confirmed.json() == {"status": "confirmed"}
        assert app.extensions["klaro"].store.read(token) is None
        assert transport.call_count == 1


def test_readme_curl_creation_error_exits_nonzero_with_json(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, transport = make_app(tmp_path, fake_clock)
    with running_server(app) as base_url:
        process = start_curl(base_url, invalid=True)
        stdout, _stderr = (part.decode() for part in process.communicate(timeout=10))
        assert process.returncode != 0
        assert json.loads(stdout)["error"]["code"] == "invalid_request"
        assert "Location" not in stdout
        assert transport.call_count == 0


def test_rich_create_wait_restart_and_explicit_confirmation(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, transport = make_app(tmp_path, fake_clock, heartbeat_seconds=60)
    token = "0" * 43
    with running_server(app) as base_url:
        process = start_curl(base_url, rich=True, recommendations=True)
        try:
            wait_for_status(process)
            response = app.test_client().post(
                f"/{token}",
                data={
                    "q1": "other",
                    "q1-other": " sparkling water ",
                    "q1-comment": " no ice ",
                    "q2": ["1", "other"],
                    "q2-other": " corn ",
                    "q2-comment": " dairy-free ",
                },
            )
            assert response.status_code == 200
            stdout, _ = (part.decode() for part in process.communicate(timeout=10))
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate(timeout=5)
        assert process.returncode == 0
        lines = stdout.splitlines()
        answer_index = lines.index("event: answer")
        answer = json.loads(lines[answer_index + 1].removeprefix("data: "))
        assert answer["questions"][0]["answered"] == []
        assert answer["questions"][0]["other"] == "sparkling water"
        assert answer["questions"][0]["comment"] == "no ice"
        assert answer["questions"][1]["answered"] == ["rice"]
        assert answer["questions"][1]["other"] == "corn"
        assert answer["questions"][1]["comment"] == "dairy-free"
        assert [question["recommendations"] for question in answer["questions"]] == [[1, 2], [2]]
        assert answer["answered_at"] == "2026-10-25T12:00:00Z"

        restarted, _ = make_app(tmp_path, fake_clock)
        assert restarted.test_client().get(f"/{token}?answer_only=1").json == answer
        confirmed = requests.post(f"{base_url}/{token}?confirmed=1", timeout=5)
        assert confirmed.status_code == 200
        assert restarted.extensions["klaro"].store.read(token) is None
        assert transport.call_count == 1
