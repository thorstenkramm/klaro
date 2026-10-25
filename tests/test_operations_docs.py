from __future__ import annotations

import os
import re
import stat
import subprocess
import tomllib
from pathlib import Path
from unittest.mock import Mock

from klaro.config import KlaroConfig, load_config
from klaro.models import Question
from klaro.pushover import CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS
from klaro.scheduler import CleanupScheduler
from klaro.sse import RETRY_FRAME
from klaro.storage import FileStore

README = (Path(__file__).parent.parent / "README.md").read_text()
OPERATIONS = [
    "development",
    "environment",
    "filesystem-setup",
    "production",
    "backup",
    "rollback",
]


def operation(name: str) -> str:
    match = re.search(
        rf"<!-- operation:{re.escape(name)} -->\s*```shell\n(.*?)```",
        README,
        re.DOTALL,
    )
    assert match is not None, f"Missing operation example {name}"
    return match.group(1).strip()


def run_operations(*names: str, root: Path, cwd: Path) -> None:
    script = "\n".join(operation(name) for name in names)
    environment = os.environ.copy()
    environment["KLARO_ROOT"] = str(root)
    subprocess.run(
        ["bash", "-euo", "pipefail", "-c", script],
        cwd=cwd,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_every_shell_example_has_valid_syntax() -> None:
    for name in OPERATIONS:
        subprocess.run(["bash", "-n", "-c", operation(name)], check=True)


def test_filesystem_backup_and_rollback_examples_in_clean_paths(tmp_path: Path) -> None:
    repository = Path(__file__).parent.parent
    root = tmp_path / "runtime"
    run_operations("environment", "filesystem-setup", root=root, cwd=repository)
    data = root / "data"
    config_path = root / "klaro.toml"

    assert mode(root) == mode(data) == 0o700
    assert mode(config_path) == 0o600
    assert root.stat().st_uid == data.stat().st_uid == os.getuid()

    config_path.write_text(
        f"""[pushover]
app_token = "{"a" * 30}"

[klaro]
data_dir = "{data}"
public_address = "https://klaro.example.com"
"""
    )
    assert load_config(config_path).klaro.data_dir == data
    token = "o" * 43
    store = FileStore(data, token_factory=lambda: token)
    store.create_pending(
        questions=[Question(id="q1", name="Drink?", kind="radio", answers=("beer", "water"))],
        questioner="Operations test",
        lifetime_seconds=60,
    )
    store.publish(token)
    record_path = store.directory / f"{token}.json"
    assert mode(record_path) == 0o600

    run_operations("environment", "backup", "rollback", root=root, cwd=repository)

    relative_record = record_path.relative_to(data)
    backup = root / "backup" / relative_record
    restored = root / "restored-data" / relative_record
    assert backup.read_bytes() == restored.read_bytes() == record_path.read_bytes()
    assert mode(root / "backup") == mode(root / "restored-data") == 0o700
    assert mode(backup) == mode(restored) == 0o600
    assert FileStore(root / "restored-data").read(token) is not None


def test_documented_start_command_and_wheel_match_verified_production_path() -> None:
    production = operation("production")
    project = tomllib.loads((Path(__file__).parent.parent / "pyproject.toml").read_text())[
        "project"
    ]
    wheel = f"klaro-{project['version']}-py3-none-any.whl"

    assert "uv build" in production
    assert 'uv venv "$KLARO_VENV"' in production
    assert 'uv pip install --python "$KLARO_VENV/bin/python" "$KLARO_WHEEL"' in production
    assert f'KLARO_WHEEL="$PWD/dist/{wheel}"' in operation("environment")
    assert '"$KLARO_VENV/bin/klaro" --config "$KLARO_CONFIG"' in production
    assert "uv run klaro --config ./klaro.toml" in README
    assert " --workers " not in production


def test_documented_timeouts_and_cleanup_values_match_implementation(tmp_path: Path) -> None:
    defaults = KlaroConfig(data_dir=tmp_path, public_address="https://klaro.example.com")

    assert defaults.lifetime_seconds == 86_400
    assert defaults.sse_heartbeat_seconds == 15
    assert CleanupScheduler(Mock()).interval_seconds == 30
    assert (CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS) == (3.05, 15.0)
    assert RETRY_FRAME == "retry: 5000\n\n"
    for text in [
        "every 30 seconds",
        "3.05-second connect timeout",
        "15-second read timeout",
        "five-second",
        "86,400 seconds",
        "proxy_buffering off",
        "proxy_read_timeout 75s",
        "reset on restart",
        "one gevent worker",
        "dead link",
    ]:
        assert text in README
