"""Unreadable records behave like unknown tokens, are logged once, and are deleted on time."""

from __future__ import annotations

import json
import logging
import os

import pytest

from klaro.filestore import FileStore, UnreadableRecord
from tests.app_helpers import make_app
from tests.helpers import FakeClock

TOKEN = "u" * 43
CORRUPT_CONTENTS = {
    "invalid-json": b"{not json",
    "invalid-utf8": b"\xff\xfe\x00",
    "wrong-version": json.dumps({"version": 3, "status": "answered"}).encode(),
    "json-list": b"[1, 2, 3]",
    "missing-fields": json.dumps({"version": 4}).encode(),
}


def write_corrupt(store: FileStore, contents: bytes, clock: FakeClock) -> os.PathLike:
    path = store.directory / f"{TOKEN}.json"
    path.write_bytes(contents)
    modified = clock.wall().timestamp()
    os.utime(path, (modified, modified))
    return path


@pytest.mark.parametrize("contents", CORRUPT_CONTENTS.values(), ids=CORRUPT_CONTENTS.keys())
def test_unreadable_records_return_the_generic_404_on_every_route(
    tmp_path, fake_clock: FakeClock, contents: bytes
) -> None:
    app, transport = make_app(tmp_path, fake_clock)
    store = app.extensions["klaro"].store
    path = write_corrupt(store, contents, fake_clock)
    client = app.test_client()
    unknown = client.get("/" + "z" * 43, headers={"Accept": "application/json"})

    responses = [
        client.get(f"/{TOKEN}", headers={"Accept": "application/json"}),
        client.get(f"/{TOKEN}?answer_only=1"),
        client.get(f"/{TOKEN}", headers={"Accept": "text/event-stream"}),
        client.post(f"/{TOKEN}", data={"q1": "1"}),
        client.post(f"/{TOKEN}?confirmed=1"),
    ]

    for response in responses:
        assert response.status_code == 404
        assert response.get_data() == unknown.get_data()
    assert path.exists()
    with pytest.raises(UnreadableRecord):
        store.read(TOKEN)
    transport.assert_not_called()


def test_unreadable_record_is_logged_once_without_its_token(
    tmp_path, fake_clock: FakeClock, caplog
) -> None:
    store = FileStore(tmp_path, clock=fake_clock, unreadable_retention_seconds=60)
    write_corrupt(store, CORRUPT_CONTENTS["invalid-json"], fake_clock)
    caplog.set_level(logging.WARNING, logger="klaro.filestore")

    for _ in range(3):
        store.cleanup_expired()

    messages = [record.getMessage() for record in caplog.records]
    assert len(messages) == 1
    assert "unreadable questionnaire record" in messages[0]
    assert "deleted 60 seconds after its last modification" in messages[0]
    assert TOKEN not in caplog.text


def test_unreadable_record_is_deleted_by_cleanup_after_its_retention(
    tmp_path, fake_clock: FakeClock, caplog
) -> None:
    store = FileStore(tmp_path, clock=fake_clock, unreadable_retention_seconds=60)
    path = write_corrupt(store, CORRUPT_CONTENTS["wrong-version"], fake_clock)
    caplog.set_level(logging.WARNING, logger="klaro.filestore")

    fake_clock.advance(59)
    store.cleanup_expired()
    assert path.exists()

    fake_clock.advance(1)
    store.cleanup_expired()

    assert not path.exists()
    assert "Deleted an unreadable questionnaire record" in caplog.text
    assert TOKEN not in caplog.text
    assert store._reported_unreadable == set()


def test_recovery_on_restart_deletes_unreadable_records_past_retention(
    tmp_path, fake_clock: FakeClock
) -> None:
    first = FileStore(tmp_path, clock=fake_clock, unreadable_retention_seconds=60)
    path = write_corrupt(first, CORRUPT_CONTENTS["json-list"], fake_clock)

    FileStore(tmp_path, clock=fake_clock, unreadable_retention_seconds=60)
    assert path.exists()

    fake_clock.advance(60)
    FileStore(tmp_path, clock=fake_clock, unreadable_retention_seconds=60)
    assert not path.exists()
