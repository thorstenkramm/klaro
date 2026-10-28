from __future__ import annotations

from io import BytesIO
from urllib.parse import urlencode

import pytest
from werkzeug.test import EnvironBuilder

from klaro.app import MAX_ANSWER_BODY_BYTES
from tests.app_helpers import make_app, post_creation
from tests.helpers import FakeClock
from tests.test_text_answers import rich_token


def answer_body(size: int, content_type: str = "application/x-www-form-urlencoded") -> bytes:
    if content_type == "application/x-www-form-urlencoded":
        prefix = b"q1=1&q2=1&pad="
        return prefix + b"x" * (size - len(prefix))
    boundary = b"klaro-boundary"
    parts = (
        b"--"
        + boundary
        + b'\r\nContent-Disposition: form-data; name="q1"\r\n\r\n1\r\n'
        + b"--"
        + boundary
        + b'\r\nContent-Disposition: form-data; name="q2"\r\n\r\n1\r\n'
        + b"--"
        + boundary
        + b'\r\nContent-Disposition: form-data; name="pad"\r\n\r\n'
    )
    suffix = b"\r\n--" + boundary + b"--\r\n"
    return parts + b"x" * (size - len(parts) - len(suffix)) + suffix


@pytest.mark.parametrize(
    "content_type",
    ["application/x-www-form-urlencoded", "multipart/form-data; boundary=klaro-boundary"],
)
def test_answer_cap_boundaries_for_urlencoded_and_multipart(
    tmp_path, fake_clock: FakeClock, content_type: str
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = rich_token(client)
    exact = client.post(
        f"/{token}",
        data=answer_body(MAX_ANSWER_BODY_BYTES, content_type),
        content_type=content_type,
        headers={"Accept": "application/json"},
    )
    assert exact.status_code == 422
    assert app.extensions["klaro"].store.read(token).answers is None

    oversized = client.post(
        f"/{token}",
        data=answer_body(MAX_ANSWER_BODY_BYTES + 1, content_type),
        content_type=content_type,
        headers={"Accept": "application/json"},
    )
    assert oversized.status_code == 413
    assert oversized.json == {
        "error": {
            "code": "payload_too_large",
            "message": "Request body exceeds 524,288 bytes.",
        }
    }
    assert app.extensions["klaro"].store.read(token).answers is None


@pytest.mark.parametrize("declared_length", ["missing", "overreported"])
def test_streamed_answer_cap_does_not_trust_content_length(
    tmp_path, fake_clock: FakeClock, declared_length: str
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = rich_token(client)
    body = answer_body(MAX_ANSWER_BODY_BYTES + 100)
    environ = EnvironBuilder(
        path=f"/{token}",
        method="POST",
        input_stream=BytesIO(body),
        content_type="application/x-www-form-urlencoded",
        headers={"Accept": "application/json"},
    ).get_environ()
    environ["CONTENT_LENGTH"] = "" if declared_length == "missing" else str(len(body) + 1000)
    response = client.open(environ)
    assert response.status_code == 413
    assert response.json["error"]["message"] == "Request body exceeds 524,288 bytes."
    assert app.extensions["klaro"].store.read(token).answers is None


def test_answer_cap_is_independent_of_creation_cap(tmp_path, fake_clock: FakeClock) -> None:
    questions = [
        {
            "name": f"Question {index}",
            "type": "radio",
            "answers": ["one", "two"],
            "allow_other": True,
            "allow_comments": True,
        }
        for index in range(6)
    ]
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = post_creation(client, body={"questions": questions}).json["url"].rsplit("/", 1)[-1]
    fields = []
    for index in range(1, 7):
        fields.extend(
            [
                (f"q{index}", "other"),
                (f"q{index}-other", "😀" * 2_000),
                (f"q{index}-comment", "😀" * 2_000),
            ]
        )
    body = urlencode(fields).encode()
    assert 65_536 < len(body) < MAX_ANSWER_BODY_BYTES
    response = client.post(f"/{token}", data=body, content_type="application/x-www-form-urlencoded")
    assert response.status_code == 200
    assert app.extensions["klaro"].store.read(token).answers["q6"].comment == "😀" * 2_000


def test_worst_case_valid_unicode_fields_can_exceed_aggregate_cap(
    tmp_path, fake_clock: FakeClock
) -> None:
    questions = [
        {
            "name": f"Question {index}",
            "type": "radio",
            "answers": ["one", "two"],
            "allow_other": True,
            "allow_comments": True,
        }
        for index in range(20)
    ]
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = post_creation(client, body={"questions": questions}).json["url"].rsplit("/", 1)[-1]
    fields = []
    for index in range(1, 21):
        fields.extend(
            [
                (f"q{index}", "other"),
                (f"q{index}-other", "😀" * 2_000),
                (f"q{index}-comment", "😀" * 2_000),
            ]
        )
    body = urlencode(fields).encode()
    assert len(body) > MAX_ANSWER_BODY_BYTES
    response = client.post(
        f"/{token}",
        data=body,
        content_type="application/x-www-form-urlencoded",
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 413
    assert app.extensions["klaro"].store.read(token).answers is None


def test_full_page_413_is_understandable_and_does_not_echo_body(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = rich_token(client)
    body = answer_body(MAX_ANSWER_BODY_BYTES + 1)
    response = client.post(f"/{token}", data=body, content_type="application/x-www-form-urlencoded")
    assert response.status_code == 413
    assert "This request is too large" in response.text
    assert "524,288 bytes" in response.text
    assert "browser’s Back button" in response.text  # noqa: RUF001 - typographic apostrophe
    assert body[-100:].decode() not in response.text
    assert response.json is None


def test_confirmation_retains_creation_body_cap(tmp_path, fake_clock: FakeClock) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = post_creation(client).json["url"].rsplit("/", 1)[-1]
    assert client.post(f"/{token}", data={"q1": "1", "q2": "1"}).status_code == 200
    response = client.post(f"/{token}?confirmed=1", data=b"x" * 65_537)
    assert response.status_code == 413
    assert response.json["error"]["message"] == "Request body exceeds 65,536 bytes."
    assert app.extensions["klaro"].store.read(token).status == "answered"
