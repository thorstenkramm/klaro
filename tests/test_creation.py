from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import Mock

import pytest

from klaro.config import Config, KlaroConfig, PushoverConfig
from klaro.creation import QuestionnaireCreator
from klaro.models import Question
from klaro.pushover import (
    PushoverClient,
    PushoverError,
    PushoverRecipientRejected,
)
from klaro.storage import FileStore, QuestionnaireNotFound
from tests.helpers import FakeClock

QUESTION = Question(id="q1", name="Drink?", kind="radio", answers=("beer", "water"))
TOKEN = "c" * 43


def setup_creator(tmp_path: Path, transport) -> tuple[QuestionnaireCreator, FileStore]:
    config = Config(
        pushover=PushoverConfig(app_token="a" * 30),
        klaro=KlaroConfig(
            data_dir=tmp_path / "data",
            public_address="https://klaro.example.com",
            lifetime_seconds=60,
        ),
    )
    store = FileStore(config.klaro.data_dir, token_factory=lambda: TOKEN, clock=FakeClock())
    notifier = PushoverClient(config.pushover, transport=transport)
    return QuestionnaireCreator(config, store, notifier), store


def pushover_response(status: int = 200, payload=None) -> Mock:
    result = Mock()
    result.status_code = status
    result.json.return_value = payload or {"status": 1, "request": "request-id"}
    return result


def test_acceptance_publishes_previously_invisible_pending_record(tmp_path: Path) -> None:
    observed = {}

    def transport(url, *, data, timeout, verify) -> Mock:
        token = data["url"].rsplit("/", 1)[-1]
        observed["token"] = token
        observed["stored"] = store.read(token)
        with pytest.raises(QuestionnaireNotFound):
            store.get_public(token)
        return pushover_response()

    creator, store = setup_creator(tmp_path, transport)

    result = creator.create(recipient="u" * 30, questioner="Dinner mate", questions=[QUESTION])

    assert observed["token"] == TOKEN
    assert observed["stored"].status == "pending"
    assert result.url == f"https://klaro.example.com/{TOKEN}"
    assert result.record.status == "awaiting_answer"
    assert result.record.pushover_request == "request-id"
    assert store.get_public(TOKEN) == result.record


@pytest.mark.parametrize(
    "response,exception_type,http_status",
    [
        (
            pushover_response(
                400, {"status": 0, "user": "invalid", "errors": ["user identifier is invalid"]}
            ),
            PushoverRecipientRejected,
            422,
        ),
        (pushover_response(503, {"status": 0}), PushoverError, 502),
    ],
)
def test_rejection_and_upstream_failure_delete_pending_and_map_errors(
    tmp_path: Path, response: Mock, exception_type: type[Exception], http_status: int
) -> None:
    transport = Mock(return_value=response)
    creator, store = setup_creator(tmp_path, transport)

    with pytest.raises(exception_type) as caught:
        creator.create(recipient="u" * 30, questioner="Dinner mate", questions=[QUESTION])

    assert caught.value.http_status == http_status
    assert store.read(TOKEN) is None
    assert list(store.directory.iterdir()) == []
    assert transport.call_count == 1


def test_ambiguous_transport_failure_deletes_pending(tmp_path: Path) -> None:
    transport = Mock(side_effect=PushoverError("ambiguous result"))
    creator, store = setup_creator(tmp_path, transport)

    with pytest.raises(PushoverError, match="ambiguous"):
        creator.create(recipient="u" * 30, questioner="Dinner mate", questions=[QUESTION])

    assert store.read(TOKEN) is None


def test_creation_does_not_log_url_or_secrets(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    transport = Mock(
        return_value=pushover_response(
            400, {"status": 0, "user": "invalid", "errors": ["user identifier is invalid"]}
        )
    )
    creator, _ = setup_creator(tmp_path, transport)

    with pytest.raises(PushoverRecipientRejected):
        creator.create(recipient="u" * 30, questioner="Dinner mate", questions=[QUESTION])

    assert TOKEN not in caplog.text
    assert "a" * 30 not in caplog.text
    assert "u" * 30 not in caplog.text
