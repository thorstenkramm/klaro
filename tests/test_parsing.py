from __future__ import annotations

import json

import pytest

from klaro.parsing import MAX_BODY_BYTES, ParseError, parse_questionnaire_body

EXPECTED = {
    "questions": [
        {
            "name": "Drink?",
            "type": "radio",
            "answers": ["beer", "water"],
        },
        {
            "name": "Sides?",
            "type": "checkbox",
            "answers": ["rice", "salad"],
        },
    ]
}


def test_json_yaml_parity() -> None:
    json_body = json.dumps(EXPECTED).encode()
    yaml_body = b"""questions:
  - name: Drink?
    type: radio
    answers: [beer, water]
  - name: Sides?
    type: checkbox
    answers: [rice, salad]
"""

    assert parse_questionnaire_body(json_body, "application/json") == EXPECTED
    assert parse_questionnaire_body(yaml_body, "application/yaml; charset=utf-8") == EXPECTED


@pytest.mark.parametrize(
    "content_type", ["text/plain", "application/x-yaml", "", "application/xml"]
)
def test_unsupported_media_type(content_type: str) -> None:
    with pytest.raises(ParseError) as caught:
        parse_questionnaire_body(b"{}", content_type)
    assert caught.value.status == 415
    assert caught.value.code == "unsupported_media_type"


def test_body_limit_is_enforced_before_parsing() -> None:
    with pytest.raises(ParseError) as caught:
        parse_questionnaire_body(b"x" * (MAX_BODY_BYTES + 1), "application/json")
    assert caught.value.status == 413
    assert caught.value.code == "payload_too_large"


def test_exact_body_limit_can_be_parsed() -> None:
    body = b"{}"
    body += b" " * (MAX_BODY_BYTES - len(body))
    assert parse_questionnaire_body(body, "application/json") == {}


@pytest.mark.parametrize("body", [b"", b" \n\t", b"\xff"])
def test_empty_or_non_utf8_bodies(body: bytes) -> None:
    with pytest.raises(ParseError, match=r"body|UTF-8"):
        parse_questionnaire_body(body, "application/json")


def test_non_utf8_charset_is_rejected() -> None:
    with pytest.raises(ParseError, match="UTF-8"):
        parse_questionnaire_body(b"{}", "application/json; charset=iso-8859-1")


@pytest.mark.parametrize(
    ("body", "content_type"),
    [
        (b'{"questions": [], "questions": []}', "application/json"),
        (b"questions: []\nquestions: []\n", "application/yaml"),
        (b'{"outer": {"key": 1, "key": 2}}', "application/json"),
        (b"outer:\n  key: 1\n  key: 2\n", "application/yaml"),
    ],
)
def test_duplicate_keys_are_rejected(body: bytes, content_type: str) -> None:
    with pytest.raises(ParseError, match=r"[Dd]uplicate"):
        parse_questionnaire_body(body, content_type)


def test_safe_yaml_rejects_object_construction() -> None:
    body = b'!!python/object/apply:os.system ["touch /tmp/klaro-should-not-exist"]'
    with pytest.raises(ParseError):
        parse_questionnaire_body(body, "application/yaml")


@pytest.mark.parametrize("body", [b"{", b"[1, 2", b'{"unterminated": }'])
def test_malformed_json(body: bytes) -> None:
    with pytest.raises(ParseError):
        parse_questionnaire_body(body, "application/json")


def test_malformed_yaml() -> None:
    with pytest.raises(ParseError):
        parse_questionnaire_body(b"questions: [unterminated", "application/yaml")
