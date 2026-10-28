from __future__ import annotations

import threading
from contextlib import contextmanager

from werkzeug.serving import make_server

from tests.app_helpers import post_creation


@contextmanager
def running_server(app):
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def token_for(app, body=None) -> str:
    """Create a questionnaire through the API and return its token."""
    return post_creation(app.test_client(), body=body).json["url"].rsplit("/", 1)[-1]


def collect_console_errors(page) -> list[str]:
    """Record browser console errors for the lifetime of the page."""
    errors: list[str] = []
    page.on(
        "console", lambda message: errors.append(message.text) if message.type == "error" else None
    )
    return errors


def csp_violations(console_errors: list[str]) -> list[str]:
    return [
        message
        for message in console_errors
        if "Content Security Policy" in message or "Refused to" in message
    ]


def submit_answers(page):
    """Click "Send answers" and return the resulting POST response."""
    with page.expect_response(lambda response: response.request.method == "POST") as pending:
        page.get_by_role("button", name="Send answers").click()
    return pending.value
