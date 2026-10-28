"""HTMX swaps move focus to the result, announce it, and never submit twice."""

from __future__ import annotations

import re

from tests.app_helpers import make_app
from tests.browser_helpers import running_server, submit_answers, token_for
from tests.helpers import FakeClock
from tests.test_text_answers import RICH_BODY


def active_element_id(page) -> str:
    return page.evaluate("document.activeElement && document.activeElement.id")


def test_focus_moves_to_errors_then_to_the_stored_answer(
    tmp_path, fake_clock: FakeClock, browser
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    token = token_for(app)

    with running_server(app) as base_url:
        page = browser.new_page(viewport={"width": 390, "height": 844})
        try:
            page.goto(f"{base_url}/{token}", wait_until="networkidle")
            announcer = page.locator("[data-kl-announcer]")
            assert announcer.count() == 1
            assert announcer.get_attribute("aria-live") == "polite"
            assert page.locator("#questionnaire-response").get_attribute("aria-live") is None

            page.locator("#q1-option-1").check()
            assert submit_answers(page).status == 422
            page.locator("#answer-errors").wait_for()
            assert active_element_id(page) == "answer-errors"
            assert page.locator("#answer-errors").get_attribute("role") == "alert"
            assert announcer.text_content() == ""

            page.locator("#q2-option-1").check()
            assert submit_answers(page).status == 200
            page.get_by_role("heading", name="Answer stored").wait_for()
            assert active_element_id(page) == "answer-stored"
            assert announcer.count() == 1
            assert announcer.text_content() == "Answer stored"
        finally:
            page.close()


def test_duplicate_submissions_are_dropped_while_a_request_is_in_flight(
    tmp_path, fake_clock: FakeClock, browser
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    token = token_for(app)

    with running_server(app) as base_url:
        page = browser.new_page(viewport={"width": 390, "height": 844})
        posts: list[str] = []
        page.on("request", lambda request: request.method == "POST" and posts.append(request.url))
        try:
            page.goto(f"{base_url}/{token}", wait_until="networkidle")
            page.locator("#q1-option-1").check()
            page.locator("#q2-option-1").check()
            with page.expect_response(lambda response: response.request.method == "POST"):
                disabled_during_request = page.evaluate(
                    """() => {
                        const form = document.querySelector("[data-kl-form]");
                        const button = form.querySelector("button[type='submit']");
                        form.requestSubmit(button);
                        const disabled = button.disabled;
                        form.requestSubmit();
                        form.requestSubmit();
                        return disabled;
                    }"""
                )
            page.get_by_role("heading", name="Answer stored").wait_for()

            assert disabled_during_request is True
            assert posts == [f"{base_url}/{token}"]
        finally:
            page.close()


def test_htmx_configuration_disables_eval_and_script_tags(
    tmp_path, fake_clock: FakeClock, browser
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    token = token_for(app)

    with running_server(app) as base_url:
        page = browser.new_page()
        try:
            page.goto(f"{base_url}/{token}", wait_until="networkidle")
            config = page.evaluate(
                "({eval: htmx.config.allowEval, scripts: htmx.config.allowScriptTags})"
            )
            assert config == {"eval": False, "scripts": False}
        finally:
            page.close()


def failure_alert(page) -> str:
    alert = page.locator("#answer-request-failed")
    alert.wait_for(state="visible")
    assert active_element_id(page) == "answer-request-failed"
    return alert.text_content().strip()


def test_conflict_missing_and_network_failures_show_a_focused_alert(
    tmp_path, fake_clock: FakeClock, browser
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()

    with running_server(app) as base_url:
        page = browser.new_page(viewport={"width": 390, "height": 844})
        try:
            answered_elsewhere = token_for(app)
            page.goto(f"{base_url}/{answered_elsewhere}", wait_until="networkidle")
            page.locator("#q1-option-1").check()
            page.locator("#q2-option-1").check()
            assert (
                client.post(f"/{answered_elsewhere}", data={"q1": "2", "q2": "2"}).status_code
                == 200
            )
            assert submit_answers(page).status == 409
            assert "already answered" in failure_alert(page)
            assert page.locator("#q1-option-1").is_checked()

            confirmed = token_for(app)
            page.goto(f"{base_url}/{confirmed}", wait_until="networkidle")
            page.locator("#q1-option-1").check()
            page.locator("#q2-option-1").check()
            client.post(f"/{confirmed}", data={"q1": "1", "q2": "1"})
            client.post(f"/{confirmed}?confirmed=1")
            assert submit_answers(page).status == 404
            assert "no longer available" in failure_alert(page)

            offline = token_for(app)
            page.goto(f"{base_url}/{offline}", wait_until="networkidle")
            page.locator("#q1-option-1").check()
            page.locator("#q2-option-1").check()
            page.route(f"{base_url}/{offline}", lambda route: route.abort())
            page.get_by_role("button", name="Send answers").click()
            assert "could not be reached" in failure_alert(page)
            assert page.locator("#answer-request-error").is_hidden()
        finally:
            page.close()


def test_javascript_progress_matches_the_server_rule(
    tmp_path, fake_clock: FakeClock, browser
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    token = token_for(app, body=RICH_BODY)
    cases = {
        "nothing": {},
        "offered": {"q1": ["1"]},
        "blank other": {"q1": ["other"], "q1-other": ["   "]},
        "other text": {"q1": ["other"], "q1-other": ["mine"]},
        "one of two": {"q1": ["other"], "q1-other": ["mine"], "q2": ["other"], "q2-other": [" "]},
    }

    with running_server(app) as base_url:
        page = browser.new_page()
        try:
            page.goto(f"{base_url}/{token}", wait_until="networkidle")
            for name, selection in cases.items():
                server = app.test_client().post(
                    f"/{token}", data=selection, headers={"HX-Request": "true"}
                )
                assert server.status_code == 422, name
                expected = re.search(r"(\d+) of (\d+) answered", server.get_data(as_text=True))
                page.locator("[data-kl-form]").evaluate("form => form.reset()")
                for field, values in selection.items():
                    for value in values:
                        if field.endswith("-other"):
                            page.locator(f"#{field}").fill(value)
                        else:
                            page.locator(f'input[name="{field}"][value="{value}"]').check()
                page.locator("#q1-comment").dispatch_event("input")
                shown = page.locator("[data-kl-progress-count]").text_content()
                assert shown == expected.group(0), name
        finally:
            page.close()
