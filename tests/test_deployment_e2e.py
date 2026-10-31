"""Opt-in tests for a disposable Linux runner, consuming an existing release archive."""

from __future__ import annotations

import functools
import http.server
import json
import os
import re
import shutil
import stat
import subprocess
import tarfile
import threading
import tomllib
from pathlib import Path

import pytest
import requests

from tests.process_helpers import stop_process_group

pytestmark = pytest.mark.skipif(
    os.environ.get("KLARO_DEPLOYMENT_E2E") != "1",
    reason="requires disposable Linux systemd runner",
)
APP = Path("/opt/klaro")
STATE = Path("/var/lib/klaro")
CONFIG_DIR = Path("/etc/klaro")
UNIT = Path("/etc/systemd/system/klaro.service")
PYTHON = STATE / "venv/bin/python"
URL = "http://127.0.0.1:3344"
CADDY_URL = "http://localhost:8080"
CADDY_IMAGE = "caddy:2.10.2@sha256:c3d7ee5d2b11f9dc54f947f68a734c84e9c9666c92c88a7f30b9cba5da182adb"


def command(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, capture_output=True, text=True, timeout=180)


def operation(readme: str, name: str) -> str:
    match = re.search(rf"<!-- operation:{name} -->\s*```shell\n(.*?)```", readme, re.S)
    assert match is not None
    return match[1]


def ready(url: str = URL) -> None:
    # Readiness polling is confined to the shared external-process helper.
    from tests.process_helpers import wait_until_serving

    class Running:
        def poll(self):
            return None

    wait_until_serving(Running(), url, timeout=180)


@pytest.fixture(scope="module")
def deployment(tmp_path_factory):
    assert os.geteuid() == 0
    assert not any(path.exists() for path in (APP, STATE, CONFIG_DIR, UNIT)), "Use a fresh runner"
    assert command("getent", "passwd", "klaro", check=False).returncode != 0
    archive = Path(os.environ["KLARO_RELEASE_ARCHIVE"]).resolve()
    root = tmp_path_factory.mktemp("release-server")
    with tarfile.open(archive) as source:
        readme_file = source.extractfile("README.md")
        assert readme_file is not None
        readme = readme_file.read().decode()
    download = re.search(r'https://github.com/([^"\s]+\.tar\.gz)', readme)
    assert download is not None
    served = root / download[1]
    served.parent.mkdir(parents=True)
    shutil.copy2(archive, served)
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0),
        functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root)),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        install = operation(readme, "release-install").replace(
            "https://github.com",
            f"http://127.0.0.1:{server.server_port}",
        )
        command("bash", "-euo", "pipefail", "-c", install)
        config = CONFIG_DIR / "klaro.toml"
        config.write_text(
            config.read_text()
            .replace(
                "REPLACE_WITH_YOUR_PUSHOVER_APP_TOKEN",
                "a" * 30,
            )
            .replace("https://klaro.example.com", CADDY_URL)
        )
        yield readme
    finally:
        command("systemctl", "stop", "klaro", check=False)
        command("systemctl", "disable", "klaro", check=False)
        UNIT.unlink(missing_ok=True)
        command("systemctl", "daemon-reload", check=False)
        # Preserve the installed environment for the following licence-scan CI step.
        server.shutdown()
        server.server_close()
        thread.join()


def test_manual_cold_start_and_permissions(deployment: str, tmp_path: Path) -> None:
    with (tmp_path / "manual.log").open("w") as log:
        process = subprocess.Popen(
            ["bash", "-c", operation(deployment, "release-run")],
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            ready()
            assert process.poll() is None
            expected = os.environ["KLARO_RELEASE_VERSION"]
            installed = command(str(PYTHON), "-c", "import klaro; print(klaro.__version__)")
            assert installed.stdout.strip() == expected
            project = tomllib.loads((APP / "pyproject.toml").read_text())
            lock = tomllib.loads((APP / "uv.lock").read_text())
            assert project["project"]["version"] == expected
            assert next(p for p in lock["package"] if p["name"] == "klaro")["version"] == expected
            assert stat.S_IMODE((CONFIG_DIR / "klaro.toml").stat().st_mode) == 0o640
            assert stat.S_IMODE(STATE.stat().st_mode) == 0o700
            assert APP.stat().st_uid == 0
        finally:
            stop_process_group(process)


@pytest.fixture(scope="module")
def service(deployment):
    # Cold startup must work inside the sandbox, not just outside it.
    shutil.rmtree(STATE / "venv", ignore_errors=True)
    shutil.rmtree(STATE / "cache", ignore_errors=True)
    shutil.rmtree(STATE / "python", ignore_errors=True)
    command("bash", "-euo", "pipefail", "-c", operation(deployment, "systemd-service"))
    ready()
    return deployment


def test_service_one_worker_and_enabled(service) -> None:
    assert command("systemctl", "is-enabled", "klaro").stdout.strip() == "enabled"
    pid = command("systemctl", "show", "-p", "MainPID", "--value", "klaro").stdout.strip()
    assert command("ps", "-o", "user=", "-p", pid).stdout.strip() == "klaro"
    assert len(Path(f"/proc/{pid}/task/{pid}/children").read_text().split()) == 1


def seed(token: str) -> None:
    script = """
import sys
from pathlib import Path
from klaro.filestore import FileStore
from klaro.models import Question
store = FileStore(Path('/var/lib/klaro/data'), token_factory=lambda: sys.argv[1])
store.create_pending(questions=[Question(id='q1', name='Ready?', kind='radio',
    answers=('yes', 'no'))], questioner='Deployment', lifetime_seconds=3600)
store.publish(sys.argv[1])
"""
    command("runuser", "-u", "klaro", "--", str(PYTHON), "-c", script, token)


def test_restart_preserves_records(service) -> None:
    token = "r" * 43
    seed(token)
    path = STATE / "data/questionnaires" / f"{token}.json"
    before = path.read_bytes()
    command("systemctl", "restart", "klaro")
    ready()
    assert path.read_bytes() == before
    assert requests.get(f"{URL}/{token}", timeout=3).status_code == 200


def test_sandbox_and_unit_validation(service) -> None:
    command("systemd-analyze", "verify", str(UNIT))
    security = command("systemd-analyze", "security", "--no-pager", "klaro.service")
    print(security.stdout)
    pid = command("systemctl", "show", "-p", "MainPID", "--value", "klaro").stdout.strip()
    for directory in (APP, CONFIG_DIR):
        # Root inside the service mount namespace still cannot write through a read-only mount.
        denied = command(
            "nsenter",
            "--target",
            pid,
            "--mount",
            "--",
            "touch",
            str(directory / "sandbox-probe"),
            check=False,
        )
        assert denied.returncode != 0
        assert not (directory / "sandbox-probe").exists()


def test_invalid_configuration_is_logged_and_limited(service) -> None:
    config = CONFIG_DIR / "klaro.toml"
    original = config.read_bytes()
    command("systemctl", "stop", "klaro")
    try:
        config.write_text('[pushover]\napp_token="invalid"\n[klaro]\n')
        command("systemctl", "reset-failed", "klaro")
        # Subscribe to systemd completion instead of polling or sleeping through restarts.
        command("systemctl", "start", "--wait", "klaro", check=False)
        result = command("systemctl", "show", "-p", "Result", "--value", "klaro").stdout
        assert "start-limit-hit" in result
        journal = command("journalctl", "-u", "klaro", "--no-pager").stdout
        assert "pushover.app_token" in journal
        assert "a" * 30 not in journal
    finally:
        config.write_bytes(original)
        command("systemctl", "reset-failed", "klaro")
        command("systemctl", "start", "klaro")
        ready()


@pytest.fixture
def caddy(service):
    name = f"klaro-caddy-{os.getpid()}"
    base = [
        "docker",
        "run",
        "--env",
        "KLARO_SITE=http://localhost:8080",
        "--volume",
        f"{APP / 'Caddyfile'}:/etc/caddy/Caddyfile:ro",
    ]
    command(*base, "--rm", CADDY_IMAGE, "caddy", "validate", "--config", "/etc/caddy/Caddyfile")
    command(*base, "--detach", "--name", name, "--network", "host", CADDY_IMAGE)
    try:
        ready(CADDY_URL)
        yield
    finally:
        command("docker", "rm", "--force", name, check=False)


def test_caddy_replaces_forged_headers(caddy) -> None:
    statuses = [
        requests.post(
            CADDY_URL,
            headers={"X-Pushover-User": "invalid", "X-Forwarded-For": f"203.0.113.{n}"},
            timeout=3,
        ).status_code
        for n in range(6)
    ]
    assert statuses == [400] * 5 + [429]


def event(lines, expected: str):
    assert next(lines) == f"event: {expected}"
    value = json.loads(next(lines)[6:])
    assert next(lines) == ""
    return value


def test_caddy_streams_status_heartbeat_answer(caddy) -> None:
    token = "s" * 43
    seed(token)
    with requests.get(
        f"{CADDY_URL}/{token}", headers={"Accept": "text/event-stream"}, stream=True, timeout=(3, 3)
    ) as stream:
        lines = stream.iter_lines(chunk_size=1, decode_unicode=True)
        assert next(lines) == "retry: 5000"
        assert next(lines) == ""
        assert event(lines, "status")["answered_at"] is None
        # Heartbeat interval is the production default; reopen with its appropriate read timeout.
    with requests.get(
        f"{CADDY_URL}/{token}",
        headers={"Accept": "text/event-stream"},
        stream=True,
        timeout=(3, 20),
    ) as stream:
        lines = stream.iter_lines(chunk_size=1, decode_unicode=True)
        next(lines)
        next(lines)
        event(lines, "status")
        assert event(lines, "heartbeat")["time"].endswith("Z")
        answer = requests.post(f"{CADDY_URL}/{token}", data={"q1": "1"}, timeout=3)
        assert answer.status_code == 200
        assert event(lines, "answer")["answered_at"] is not None
