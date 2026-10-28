"""Redact bearer questionnaire tokens from application and access logs."""

from __future__ import annotations

import logging
import re
from typing import Any

_TOKEN_PATH = re.compile(r"/[A-Za-z0-9_-]{43}(?![A-Za-z0-9_-])", re.ASCII)
REDACTED_PATH = "/<redacted>"
_TRACEBACK_FORMATTER = logging.Formatter()


def redact_text(value: str) -> str:
    return _TOKEN_PATH.sub(REDACTED_PATH, value)


def _redact_argument(value: Any) -> Any:
    return redact_text(value) if isinstance(value, str) else value


class RedactingFilter(logging.Filter):
    """Redact formatted log text without mutating the logged objects.

    The message is formatted once, so arguments of any type (including exceptions whose
    ``str()`` contains a URL) are covered. Tracebacks, including chained causes, are
    formatted into ``exc_text``, which standard formatters reuse instead of re-formatting.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact_text(record.getMessage())
            record.args = None
        except (TypeError, ValueError):  # Mismatched arguments: logging reports them later.
            if isinstance(record.msg, str):
                record.msg = redact_text(record.msg)
            if isinstance(record.args, tuple):
                record.args = tuple(_redact_argument(value) for value in record.args)
        if record.exc_info and not record.exc_text:
            record.exc_text = _TRACEBACK_FORMATTER.formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redact_text(record.exc_text)
        if record.stack_info:
            record.stack_info = redact_text(record.stack_info)
        return True


def install_redacting_filter(logger: logging.Logger) -> None:
    if not any(isinstance(item, RedactingFilter) for item in logger.filters):
        logger.addFilter(RedactingFilter())
    for handler in logger.handlers:
        if not any(isinstance(item, RedactingFilter) for item in handler.filters):
            handler.addFilter(RedactingFilter())
