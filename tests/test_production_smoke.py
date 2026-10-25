from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import time
from pathlib import Path

import requests

from klaro.models import Question
from klaro.storage import FileStore

TOKEN = "p" * 43


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def test_klaro_cli_gevent_serves_ordinary_requests_during_open_sse(tmp_path: Path) -> None:
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    store = FileStore(tmp_path / "data", token_factory=lambda: TOKEN)
    store.create_pending(
        questions=[Question(id="q1", name="Drink?", kind="radio", answers=("beer", "water"))],
        questioner="Production test",
        lifetime_seconds=60,
    )
    store.publish(TOKEN)
    config = tmp_path / "klaro.toml"
    config.write_text(
        f"""[pushover]
app_token = "{"a" * 30}"

[klaro]
data_dir = "{tmp_path / "data"}"
public_address = "{base_url}"
listen = "127.0.0.1:{port}"
lifetime_seconds = 60
sse_heartbeat_seconds = 1
"""
    )
    environment = os.environ.copy()
    environment.pop("KLARO_CONFIG", None)
    environment["PYTHONUNBUFFERED"] = "1"
    command = ["uv", "run", "klaro", "--config", str(config)]
    log_path = tmp_path / "gunicorn.log"
    process = None
    stream = None

    with log_path.open("w") as log_file:
        try:
            process = subprocess.Popen(
                command,
                cwd=Path(__file__).parent.parent,
                env=environment,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            deadline = time.monotonic() + 20
            while True:
                if process.poll() is not None:
                    raise AssertionError(f"Gunicorn exited early with {process.returncode}")
                try:
                    ready = requests.get(f"{base_url}/static/vendor/htmx/htmx.min.js", timeout=0.5)
                    if ready.status_code == 200:
                        break
                except requests.RequestException:
                    pass
                if time.monotonic() >= deadline:
                    raise AssertionError("Gunicorn did not start within 20 seconds")
                time.sleep(0.1)

            stream = requests.get(
                f"{base_url}/{TOKEN}",
                headers={"Accept": "text/event-stream"},
                stream=True,
                timeout=(1, 10),
            )
            assert stream.status_code == 200
            assert stream.headers["X-Accel-Buffering"] == "no"
            lines = stream.iter_lines(decode_unicode=True)
            assert next(lines) == "retry: 5000"
            assert next(lines) == ""
            assert next(lines) == "event: status"
            status = json.loads(next(lines)[6:])
            assert status["status"] == "awaiting_answer"
            assert next(lines) == ""

            ordinary = requests.get(
                f"{base_url}/{TOKEN}", headers={"Accept": "application/json"}, timeout=2
            )
            static = requests.get(f"{base_url}/static/vendor/uikit/uikit.min.css", timeout=2)
            assert ordinary.status_code == 200
            assert ordinary.json()["status"] == "awaiting_answer"
            assert static.status_code == 200

            assert next(lines) == "event: heartbeat"
            heartbeat = json.loads(next(lines)[6:])
            assert heartbeat["time"].endswith("Z")
            assert next(lines) == ""
            assert requests.get(f"{base_url}/missing", timeout=2).status_code == 404
            assert process.poll() is None
        finally:
            if stream is not None:
                stream.close()
            if process is not None and process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)

    logs = log_path.read_text()
    assert logs.count("Booting worker with pid") == 1
    assert logs.count("Klaro cleanup scheduler started") == 1
    assert TOKEN not in logs
    assert "/<redacted>" in logs
    assert "a" * 30 not in logs
