"""Automated WCAG 2.x A/AA checks (axe-core) for every answering-page state."""

from __future__ import annotations

import pytest
from axe_playwright_python.sync_playwright import Axe

from klaro.limits import MAX_ANSWER_BODY_BYTES
from tests.app_helpers import make_app, post_creation
from tests.browser_helpers import running_server, submit_answers
from tests.helpers import FakeClock
from tests.test_markdown_api import MARKDOWN_BODY
from tests.test_recommendations import REC_BODY
from tests.test_text_answers import RICH_BODY

WCAG_RULES = {
    "runOnly": {
        "type": "tag",
        "values": ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"],
    },
    "resultTypes": ["violations"],
}
AXE = Axe()


def assert_accessible(page, state: str) -> None:
    results = AXE.run(page, options=WCAG_RULES)
    violations = [
        f"{violation['id']} ({violation['impact']}): {violation['help']} "
        f"-> {[node['target'] for node in violation['nodes']]}"
        for violation in results.response["violations"]
    ]
    assert violations == [], f"{state}: {violations}"


def answer_every_question(page) -> None:
    for fieldset in page.locator("fieldset").all():
        fieldset.locator("input:not([value='other'])").first.check()


@pytest.mark.parametrize(
    "body",
    [RICH_BODY, REC_BODY, MARKDOWN_BODY],
    ids=["text-answers", "recommendations", "markdown"],
)
def test_active_invalid_and_answered_states_have_no_wcag_violations(
    tmp_path, fake_clock: FakeClock, browser, body
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    created = post_creation(app.test_client(), body=body)
    assert created.status_code == 201
    token = created.json["url"].rsplit("/", 1)[-1]

    with running_server(app) as base_url:
        page = browser.new_page(viewport={"width": 320, "height": 700})
        try:
            page.goto(f"{base_url}/{token}", wait_until="networkidle")
            assert_accessible(page, "active form")

            # Skip native required-field validation to reach the server's error state.
            page.locator("[data-kl-form]").evaluate("form => { form.noValidate = true; }")
            assert submit_answers(page).status == 422
            page.locator("#answer-errors").wait_for()
            assert_accessible(page, "validation errors")

            answer_every_question(page)
            assert submit_answers(page).status == 200
            page.get_by_role("heading", name="Answer stored").wait_for()
            assert_accessible(page, "answered")
        finally:
            page.close()


def test_request_too_large_page_has_no_wcag_violations(
    tmp_path, fake_clock: FakeClock, browser
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = post_creation(client).json["url"].rsplit("/", 1)[-1]
    too_large = client.post(
        f"/{token}",
        data={"q1": "1", "q2": "x" * (MAX_ANSWER_BODY_BYTES + 1)},
        headers={"Accept": "text/html"},
    )
    assert too_large.status_code == 413

    with running_server(app) as base_url:
        # A real oversized upload stalls the development server; serve the real page
        # from the same origin instead, so its stylesheets apply as in production.
        page = browser.new_page()
        page.route(
            f"{base_url}/request-too-large",
            lambda route: route.fulfill(
                status=413, content_type="text/html", body=too_large.get_data(as_text=True)
            ),
        )
        try:
            page.goto(f"{base_url}/request-too-large", wait_until="networkidle")
            page.get_by_role("heading", name="This request is too large").wait_for()
            assert_accessible(page, "request too large")
        finally:
            page.close()
