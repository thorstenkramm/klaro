from __future__ import annotations

from unittest.mock import patch

import pytest

from klaro.models import SchemaValidationError
from klaro.validation import validate_creation_headers, validate_questioner, validate_recipient_key


@pytest.mark.parametrize("key", ["a" * 30, "Z" * 30, "0" * 30, "aB3" * 10])
def test_valid_recipient_keys(key: str) -> None:
    assert validate_recipient_key(key) == key


@pytest.mark.parametrize(
    "key",
    [None, "", "a" * 29, "a" * 31, "a" * 29 + "-", "a" * 29 + " ", "a" * 29 + "ä", 1234567890],
)
def test_invalid_recipient_keys(key: object) -> None:
    with pytest.raises(SchemaValidationError) as caught:
        validate_recipient_key(key)
    assert caught.value.field == "headers.X-Pushover-User"


def test_recipient_validation_is_case_sensitive_syntax_only() -> None:
    lower = "a" * 30
    upper = "A" * 30
    assert validate_recipient_key(lower) != validate_recipient_key(upper)


@pytest.mark.parametrize("label", ["x", "Dinner mate", " Dinner mate ", "ä" * 100])
def test_valid_questioners(label: str) -> None:
    assert validate_questioner(label) == label


@pytest.mark.parametrize("label", [None, "", " ", "\t\n", "x" * 101, 3])
def test_invalid_questioners(label: object) -> None:
    with pytest.raises(SchemaValidationError) as caught:
        validate_questioner(label)
    assert caught.value.field == "headers.X-Questioner"


def test_both_headers_are_validated() -> None:
    assert validate_creation_headers("a" * 30, "Dinner mate") == ("a" * 30, "Dinner mate")


@patch("requests.Session.post")
def test_invalid_headers_cannot_trigger_outbound_calls(mock_post) -> None:
    for recipient, questioner in [("bad", "Dinner mate"), ("a" * 30, " "), (None, None)]:
        with pytest.raises(SchemaValidationError):
            validate_creation_headers(recipient, questioner)
    mock_post.assert_not_called()
