"""Validation for caller-supplied creation headers."""

from __future__ import annotations

import re
from typing import Any

from klaro.models import SchemaValidationError

_RECIPIENT_RE = re.compile(r"^[A-Za-z0-9]{30}$", re.ASCII)


def validate_recipient_key(value: Any) -> str:
    """Validate Pushover user/group-key syntax, not account existence."""
    if not isinstance(value, str) or not _RECIPIENT_RE.fullmatch(value):
        raise SchemaValidationError(
            "headers.X-Pushover-User",
            "Must contain exactly 30 case-sensitive ASCII alphanumeric characters.",
        )
    return value


def validate_questioner(value: Any) -> str:
    """Validate and preserve the exact caller-supplied display label."""
    if value is None:
        raise SchemaValidationError("headers.X-Questioner", "This header is required.")
    if not isinstance(value, str):
        raise SchemaValidationError("headers.X-Questioner", "Must be a string.")
    if not value.strip():
        raise SchemaValidationError(
            "headers.X-Questioner", "Must contain at least one non-whitespace character."
        )
    if len(value) > 100:
        raise SchemaValidationError("headers.X-Questioner", "Must contain at most 100 characters.")
    return value


def validate_creation_headers(recipient: Any, questioner: Any) -> tuple[str, str]:
    """Validate both headers before any outbound integration can be invoked."""
    return validate_recipient_key(recipient), validate_questioner(questioner)
