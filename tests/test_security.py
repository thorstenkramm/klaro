from __future__ import annotations

import logging
from unittest.mock import Mock

from klaro.logging_utils import install_redacting_filter, redact_text
from tests.app_helpers import RECIPIENT, make_app, post_creation, pushover_response
from tests.helpers import FakeClock


def assert_security_headers(response) -> None:
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    csp = response.headers["Content-Security-Policy"]
    for directive in [
        "default-src 'none'",
        "style-src 'self'",
        "script-src 'self'",
        "connect-src 'self'",
        "form-action 'self'",
        "base-uri 'none'",
        "frame-ancestors 'none'",
        "object-src 'none'",
    ]:
        assert directive in csp


def test_security_headers_and_access_log_redaction_across_routes(
    tmp_path, fake_clock: FakeClock, caplog
) -> None:
    caplog.set_level(logging.INFO)
    app, _ = make_app(tmp_path, fake_clock, heartbeat_seconds=60)
    client = app.test_client()
    first_token = post_creation(client).json["url"].rsplit("/", 1)[-1]
    second_token = post_creation(client).json["url"].rsplit("/", 1)[-1]
    stream = client.get(f"/{second_token}", headers={"Accept": "text/event-stream"}, buffered=False)
    responses = [
        client.get(f"/{first_token}", headers={"Accept": "text/html"}),
        client.get(f"/{first_token}", headers={"Accept": "application/json"}),
        client.get(f"/{first_token}?answer_only=1"),
        client.get("/static/vendor/htmx/htmx.min.js"),
        client.post(f"/{first_token}", data={"q1": "beer"}),
        client.post(f"/{first_token}", data={"q1": "beer", "q2": "rice"}),
        client.post(f"/{first_token}?confirmed=1"),
        client.get(f"/{first_token}"),
        stream,
    ]

    for response in responses:
        assert_security_headers(response)
    stream.close()
    assert first_token not in caplog.text
    assert second_token not in caplog.text
    assert RECIPIENT not in caplog.text
    assert "a" * 30 not in caplog.text
    assert "/<redacted>" in caplog.text


def test_gunicorn_access_logger_filter_redacts_request_arguments(caplog) -> None:
    token = "s" * 43
    install_redacting_filter(logging.getLogger("gunicorn.access"))
    caplog.set_level(logging.INFO, logger="gunicorn.access")

    logging.getLogger("gunicorn.access").info(
        '"%s %s HTTP/1.1" %s', "GET", f"/{token}?answer_only=1", 200
    )

    assert token not in caplog.text
    assert "/<redacted>?answer_only=1" in caplog.text


def test_upstream_diagnostic_log_is_actionable_without_secrets(
    tmp_path, fake_clock: FakeClock, caplog
) -> None:
    caplog.set_level(logging.INFO)
    transport = Mock(return_value=pushover_response(503, {"status": 0}))
    app, _ = make_app(tmp_path, fake_clock, transport=transport)

    response = post_creation(app.test_client())

    assert response.status_code == 502
    assert "Pushover notification failed" in caplog.text
    assert "pending questionnaire discarded" in caplog.text
    assert "0" * 43 not in caplog.text
    assert RECIPIENT not in caplog.text
    assert "a" * 30 not in caplog.text


def test_path_redaction_handles_urls_files_and_boundaries() -> None:
    token = "t" * 43

    assert redact_text(f"GET /{token}?answer_only=1") == "GET /<redacted>?answer_only=1"
    assert (
        redact_text(f"https://klaro.example.com/{token}") == "https://klaro.example.com/<redacted>"
    )
    assert redact_text(f"/var/lib/klaro/{token}.json") == "/var/lib/klaro/<redacted>.json"
    assert redact_text("/" + "t" * 44) == "/" + "t" * 44
    assert redact_text("/" + "t" * 42) == "/" + "t" * 42


def test_readme_documents_shared_url_risk_and_single_submission() -> None:
    from pathlib import Path

    readme = (Path(__file__).parent.parent / "README.md").read_text()
    assert "Anyone who possesses it" in readme
    assert "exactly one valid submission" in readme
    assert "first valid submission wins atomically" in readme
