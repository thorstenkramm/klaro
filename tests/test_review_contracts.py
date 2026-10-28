"""Error contracts, deployment constraints, and single-source limits."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from klaro import limits
from klaro.config import ConfigError, parse_config
from klaro.parsing import ParseError, parse_questionnaire_body
from klaro.records import InvalidRecord, Questionnaire
from tests.app_helpers import RECIPIENT, make_app, post_creation
from tests.helpers import FakeClock
from tests.test_sse import create_token

SOURCE = Path(__file__).parent.parent / "src" / "klaro"


@pytest.mark.parametrize(
    ("content_type", "body"),
    [
        ("application/json", '{"questions":' + "[" * 20_000 + "]" * 20_000 + "}"),
        ("application/yaml", "questions: " + "[" * 20_000 + "]" * 20_000),
    ],
    ids=["json", "yaml"],
)
def test_deeply_nested_body_is_a_client_error(content_type: str, body: str) -> None:
    with pytest.raises(ParseError, match="nesting is too deep") as caught:
        parse_questionnaire_body(body.encode(), content_type)

    assert caught.value.status == 400
    assert caught.value.__cause__ is None


def test_deeply_nested_creation_returns_400_without_calling_pushover(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, transport = make_app(tmp_path, fake_clock)
    response = app.test_client().post(
        "/",
        data="{" + '"a":[' * 5_000 + "]" * 5_000 + "}",
        content_type="application/json",
        headers={"X-Pushover-User": RECIPIENT, "X-Questioner": "Dinner mate"},
    )

    assert response.status_code == 400
    assert response.json["error"]["code"] == "invalid_request"
    transport.assert_not_called()


@pytest.mark.parametrize(
    ("accept", "json_body"), [("*/*", True), ("application/json", True), ("text/html", False)]
)
def test_unexpected_errors_keep_the_json_error_contract(
    tmp_path, fake_clock: FakeClock, monkeypatch, accept: str, json_body: bool
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    app.config.update(TESTING=False, PROPAGATE_EXCEPTIONS=False)
    client = app.test_client()
    token = create_token(client)

    def broken(_token: str) -> None:
        raise RuntimeError("storage exploded")

    monkeypatch.setattr(app.extensions["klaro"].store, "get_public", broken)
    response = client.get(f"/{token}", headers={"Accept": accept})

    assert response.status_code == 500
    if json_body:
        assert response.json == {
            "error": {"code": "internal_error", "message": "An unexpected error occurred."}
        }
    else:
        assert response.mimetype == "text/html"
    assert "storage exploded" not in response.get_data(as_text=True)


def test_only_the_browser_answer_form_receives_the_html_413_page(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = create_token(client)
    browser = {"Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}
    oversized = b"x" * (limits.MAX_BODY_BYTES + 1)

    creation = client.post(
        "/",
        data=oversized,
        content_type="application/json",
        headers={**browser, "X-Pushover-User": RECIPIENT, "X-Questioner": "Dinner mate"},
    )
    confirmation = client.post(f"/{token}?confirmed=1", data=oversized, headers=browser)
    answer_form = client.post(
        f"/{token}",
        data={"q1": "1", "q2": "x" * limits.MAX_ANSWER_BODY_BYTES},
        headers=browser,
    )
    htmx_form = client.post(
        f"/{token}",
        data={"q1": "1", "q2": "x" * limits.MAX_ANSWER_BODY_BYTES},
        headers={**browser, "HX-Request": "true"},
    )

    for response in (creation, confirmation, htmx_form):
        assert response.status_code == 413
        assert response.json["error"]["code"] == "payload_too_large"
    assert answer_form.status_code == 413
    assert answer_form.mimetype == "text/html"
    assert "This request is too large" in answer_form.get_data(as_text=True)


def raw_config(tmp_path: Path, public_address: str) -> dict:
    return {
        "pushover": {"app_token": "a" * 30},
        "klaro": {"data_dir": str(tmp_path / "data"), "public_address": public_address},
    }


@pytest.mark.parametrize("address", ["https://example.org/klaro", "https://example.org/a/b/"])
def test_public_address_with_path_is_rejected(tmp_path: Path, address: str) -> None:
    with pytest.raises(ConfigError, match="must not contain a path"):
        parse_config(raw_config(tmp_path, address))


@pytest.mark.parametrize("address", ["https://example.org", "https://example.org/"])
def test_public_address_at_root_is_accepted(tmp_path: Path, address: str) -> None:
    assert parse_config(raw_config(tmp_path, address)).klaro.public_address == (
        "https://example.org"
    )


def test_limit_literals_live_only_in_the_limits_module() -> None:
    literal = re.compile(r"(?<![\w.])(?:2[_,]?000|65[_,]?536|524[_,]?288)(?![\w])")
    offenders = [
        f"{path.relative_to(SOURCE)}:{number}"
        for path in SOURCE.rglob("*")
        if path.suffix in {".py", ".html", ".js"}
        and "vendor" not in path.parts
        and path.name != "limits.py"
        for number, line in enumerate(path.read_text().splitlines(), 1)
        if literal.search(line)
    ]

    assert offenders == []


def test_text_limits_reach_the_page_from_the_limits_module(tmp_path, fake_clock) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    body = {
        "questions": [
            {
                "name": "Drink?",
                "type": "radio",
                "answers": ["beer", "water"],
                "allow_other": True,
                "allow_comments": True,
            }
        ]
    }
    url = post_creation(client, body=body).json["url"]
    page = client.get("/" + url.rsplit("/", 1)[1], headers={"Accept": "text/html"})
    html = page.get_data(as_text=True)

    maximum = limits.MAX_TEXT_CHARACTERS
    assert html.count(f'data-kl-max="{maximum}"') == 2
    assert html.count(f"0 / {maximum}") == 2
    assert f"up to {maximum:,} characters" in html


def stored_record(**question_overrides) -> dict:
    question = {
        "id": "q1",
        "name": "Drink?",
        "type": "radio",
        "answers": ["beer", "water"],
        "allow_other": False,
        "allow_comments": False,
        "recommendations": [],
        **question_overrides,
    }
    return {
        "version": 4,
        "status": "awaiting_answer",
        "created_at": "2026-10-25T12:00:00Z",
        "expires_at": "2026-10-25T12:01:00Z",
        "questioner": "Dinner mate",
        "questions": [question],
        "answers": None,
        "answered_at": None,
        "pushover_request": None,
    }


def test_stored_questions_round_trip_through_the_input_validator() -> None:
    record = Questionnaire.from_storage("t" * 43, stored_record(recommendations=[2]))

    assert json.loads(json.dumps(record.storage_dict())) == stored_record(recommendations=[2])


@pytest.mark.parametrize(
    "overrides",
    [
        {"id": "q2"},
        {"name": "x" * (limits.MAX_NAME_CHARACTERS + 1)},
        {"answers": ["only one"]},
        {"answers": ["beer", "x" * (limits.MAX_OPTION_CHARACTERS + 1)]},
        {"recommendations": [2, 1], "answers": ["beer", "water"]},
        {"recommendations": [True]},
        {"allow_other": 1},
        {"unexpected": "field"},
    ],
)
def test_stored_questions_violating_input_rules_are_rejected(overrides: dict) -> None:
    with pytest.raises(InvalidRecord):
        Questionnaire.from_storage("t" * 43, stored_record(**overrides))
