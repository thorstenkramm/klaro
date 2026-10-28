"""Content negotiation and the shared JSON error contract."""

from __future__ import annotations

from typing import Any

from flask import Response, jsonify, request


def error_response(
    code: str,
    message: str,
    status: int,
    *,
    fields: dict[str, list[str]] | None = None,
    headers: dict[str, str] | None = None,
) -> Response:
    error: dict[str, Any] = {"code": code, "message": message}
    if fields:
        error["fields"] = fields
    response = jsonify({"error": error})
    response.status_code = status
    if headers:
        response.headers.update(headers)
    return response


def not_found() -> Response:
    return error_response("not_found", "Questionnaire not found.", 404)


def state_conflict() -> Response:
    return error_response(
        "state_conflict", "The questionnaire is not in a state that allows this operation.", 409
    )


def wants_json() -> bool:
    return request.accept_mimetypes["application/json"] > request.accept_mimetypes["text/html"]


def explicitly_wants_html() -> bool:
    """Browsers list ``text/html`` explicitly; API clients such as curl send ``*/*``."""
    listed = any(mime == "text/html" for mime, _ in request.accept_mimetypes)
    return listed and not wants_json()


def wants_sse() -> bool:
    accepts = request.accept_mimetypes
    explicitly_listed = any(mime == "text/event-stream" for mime, _ in accepts)
    event_stream = accepts["text/event-stream"]
    return explicitly_listed and event_stream > max(
        accepts["application/json"],
        accepts["text/html"],
    )


def is_htmx() -> bool:
    return request.headers.get("HX-Request") == "true"
