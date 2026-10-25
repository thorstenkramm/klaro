"""Redact bearer questionnaire tokens from application and access logs."""

from __future__ import annotations

import logging
import re
from typing import Any

_TOKEN_PATH = re.compile(r"/[A-Za-z0-9_-]{43}(?![A-Za-z0-9_-])", re.ASCII)
REDACTED_PATH = "/<redacted>"


def redact_text(value: str) -> str:
    return _TOKEN_PATH.sub(REDACTED_PATH, value)


def _redact_argument(value: Any) -> Any:
    return redact_text(value) if isinstance(value, str) else value


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_text(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(_redact_argument(value) for value in record.args)
        elif isinstance(record.args, dict):
            record.args = {key: _redact_argument(value) for key, value in record.args.items()}
        if record.exc_text:
            record.exc_text = redact_text(record.exc_text)
        if record.exc_info and record.exc_info[1] is not None:
            exception = record.exc_info[1]
            exception.args = tuple(_redact_argument(value) for value in exception.args)
        return True


def install_redacting_filter(logger: logging.Logger) -> None:
    if not any(isinstance(item, RedactingFilter) for item in logger.filters):
        logger.addFilter(RedactingFilter())
    for handler in logger.handlers:
        if not any(isinstance(item, RedactingFilter) for item in handler.filters):
            handler.addFilter(RedactingFilter())
