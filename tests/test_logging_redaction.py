"""Bearer questionnaire URLs must never reach log output, whatever the record shape."""

from __future__ import annotations

import io
import logging

import pytest

from klaro.logging_utils import REDACTED_PATH, RedactingFilter, install_redacting_filter

TOKEN = "A" * 21 + "_-" + "b" * 20
URL = f"https://klaro.example.com/{TOKEN}"


def fail(error: Exception) -> None:
    raise error


def fail_with_cause(error: Exception, cause: Exception) -> None:
    try:
        fail(cause)
    except type(cause) as caught:
        raise error from caught


@pytest.fixture
def captured():
    logger = logging.getLogger(f"klaro.test.{id(object())}")
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger.addHandler(handler)
    install_redacting_filter(logger)
    yield logger, stream
    logger.removeHandler(handler)


def test_message_tuple_and_mapping_arguments_are_redacted(captured) -> None:
    logger, stream = captured

    logger.info(f"GET /{TOKEN} 200")
    logger.info("GET %s %d", f"/{TOKEN}?answer_only=1", 200)
    logger.info("%(path)s answered", {"path": f"/{TOKEN}", "count": 1})

    output = stream.getvalue()
    assert TOKEN not in output
    assert output.count(REDACTED_PATH) == 3
    assert "?answer_only=1" in output


def test_exception_arguments_and_cached_traceback_text_are_redacted(captured) -> None:
    logger, stream = captured

    try:
        fail(RuntimeError(f"failed for {URL}", 42))
    except RuntimeError:
        logger.exception("Request failed")

    record = logging.LogRecord("x", logging.ERROR, __file__, 1, "cached", None, None)
    record.exc_text = f"Traceback mentions {URL}"
    RedactingFilter().filter(record)

    assert TOKEN not in stream.getvalue()
    assert "RuntimeError" in stream.getvalue()
    assert TOKEN not in record.exc_text


def test_chained_tracebacks_are_redacted_without_mutating_exceptions(captured) -> None:
    logger, stream = captured
    cause = ValueError(f"cause mentions {URL}")
    try:
        fail_with_cause(RuntimeError(f"wrapper mentions /{TOKEN}"), cause)
    except RuntimeError as error:
        wrapper = error
        logger.exception("Failed: %s", wrapper)
        logger.info(f"Stack near /{TOKEN}", stack_info=True)

    output = stream.getvalue()
    assert TOKEN not in output
    assert "The above exception was the direct cause" in output
    assert "Stack (most recent call last)" in output
    assert cause.args == (f"cause mentions {URL}",)
    assert wrapper.args == (f"wrapper mentions /{TOKEN}",)


def test_exception_objects_as_arguments_are_redacted(captured) -> None:
    logger, stream = captured

    logger.warning("Upstream said %s", ConnectionError(f"GET {URL} failed"))

    assert (
        stream.getvalue().strip() == "Upstream said GET https://klaro.example.com/<redacted> failed"
    )


def test_filter_runs_safely_twice_and_keeps_literal_percent_signs(captured) -> None:
    _logger, _stream = captured
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "100%% of /%s", (TOKEN,), None)
    RedactingFilter().filter(record)
    RedactingFilter().filter(record)

    assert record.getMessage() == f"100% of {REDACTED_PATH}"


def test_mismatched_arguments_do_not_raise_inside_the_filter() -> None:
    record = logging.LogRecord("x", logging.INFO, __file__, 1, f"/{TOKEN} %s %s", ("one",), None)

    assert RedactingFilter().filter(record) is True
    assert TOKEN not in record.msg


def test_non_token_paths_and_non_string_arguments_are_unchanged(captured) -> None:
    logger, stream = captured
    short = "A" * 42
    long = "A" * 44

    logger.info("%s %s %s", f"/{short}", f"/{long}", 7)

    assert stream.getvalue().strip() == f"/{short} /{long} 7"


def test_installation_is_idempotent_and_covers_existing_handlers() -> None:
    logger = logging.getLogger("klaro.test.install")
    handler = logging.StreamHandler(io.StringIO())
    logger.addHandler(handler)
    try:
        install_redacting_filter(logger)
        install_redacting_filter(logger)

        assert sum(isinstance(item, RedactingFilter) for item in logger.filters) == 1
        assert sum(isinstance(item, RedactingFilter) for item in handler.filters) == 1
    finally:
        logger.removeHandler(handler)
        logger.filters.clear()
