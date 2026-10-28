from __future__ import annotations

import itertools
import json
from pathlib import Path
from unittest.mock import Mock

from klaro.app import create_app
from klaro.config import Config, KlaroConfig, PushoverConfig
from klaro.pushover import PushoverClient
from tests.helpers import FakeClock

IP = "192.0.2.10"
QUESTIONER = "Dinner mate"
RECIPIENT = "u" * 30
VALID_BODY = {
    "questions": [
        {"name": "Drink?", "type": "radio", "answers": ["beer", "water"]},
        {"name": "Sides?", "type": "checkbox", "answers": ["rice", "salad"]},
    ]
}


def pushover_response(status: int = 200, payload=None) -> Mock:
    response = Mock()
    response.status_code = status
    response.json.return_value = payload or {"status": 1, "request": "request-id"}
    return response


def make_app(
    tmp_path: Path,
    clock: FakeClock,
    *,
    transport: Mock | None = None,
    questioners: tuple[str, ...] | None = None,
    trusted_proxies=(),
    heartbeat_seconds: int = 15,
):
    config = Config(
        pushover=PushoverConfig(app_token="a" * 30),
        klaro=KlaroConfig(
            data_dir=tmp_path / "data",
            public_address="https://klaro.example.com",
            lifetime_seconds=60,
            sse_heartbeat_seconds=heartbeat_seconds,
            questioners=questioners,
            trusted_proxies=trusted_proxies,
        ),
    )
    sequence = itertools.count()

    def token_factory() -> str:
        return f"{next(sequence):043d}"

    actual_transport = transport or Mock(return_value=pushover_response())
    notifier = PushoverClient(config.pushover, transport=actual_transport)
    app = create_app(config, clock=clock, notifier=notifier, token_factory=token_factory)
    app.config.update(TESTING=True)
    return app, actual_transport


def post_creation(
    client, *, body=None, questioner=QUESTIONER, recipient=RECIPIENT, ip=IP, headers=None
):
    return client.post(
        "/",
        data=json.dumps(VALID_BODY if body is None else body),
        content_type="application/json",
        headers={"X-Pushover-User": recipient, "X-Questioner": questioner, **(headers or {})},
        environ_base={"REMOTE_ADDR": ip},
    )
