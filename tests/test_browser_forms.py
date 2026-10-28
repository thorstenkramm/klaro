from __future__ import annotations

from tests.app_helpers import make_app
from tests.browser_helpers import (
    collect_console_errors,
    csp_violations,
    running_server,
    submit_answers,
    token_for,
)
from tests.helpers import FakeClock
from tests.test_text_answers import rich_token


def test_narrow_viewport_and_keyboard_submission(tmp_path, fake_clock: FakeClock, browser) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    token = token_for(app)

    with running_server(app) as base_url:
        page = browser.new_page(viewport={"width": 320, "height": 700})
        try:
            page.goto(f"{base_url}/{token}", wait_until="networkidle")
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            assert page.locator("input").count() == 4
            for index in range(page.locator("input").count()):
                assert page.locator("input").nth(index).is_visible()

            page.locator("#q1-option-1").focus()
            page.keyboard.press("Space")
            assert page.locator("#q1-option-1").is_checked()
            page.locator("#q2-option-1").focus()
            page.keyboard.press("Space")
            assert page.locator("#q2-option-1").is_checked()
            page.get_by_role("button", name="Send answers").focus()
            page.keyboard.press("Enter")

            page.get_by_role("heading", name="Answer stored").wait_for()
            assert page.locator("input").count() == 0
            assert page.locator("form").count() == 0
            assert page.get_by_text("beer", exact=True).is_visible()
        finally:
            page.close()


def test_htmx_validation_and_success_use_fragments(
    tmp_path, fake_clock: FakeClock, browser
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    token = token_for(app)

    with running_server(app) as base_url:
        page = browser.new_page(viewport={"width": 390, "height": 844})
        try:
            page.goto(f"{base_url}/{token}", wait_until="networkidle")
            page.locator("#q1-option-1").check()
            validation = submit_answers(page)
            assert validation.status == 422
            assert "<html" not in validation.text()

            page.locator("#q2-error").wait_for()
            assert page.locator("#q1-option-1").is_checked()
            assert page.locator("form").is_visible()
            page.locator("#q2-option-1").check()
            success = submit_answers(page)
            assert success.status == 200
            assert "<html" not in success.text()
            page.get_by_role("heading", name="Answer stored").wait_for()
            assert page.locator("form").count() == 0
        finally:
            page.close()


def test_no_javascript_fallback_shows_errors_then_succeeds(
    tmp_path, fake_clock: FakeClock, browser
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    token = token_for(app)

    with running_server(app) as base_url:
        context = browser.new_context(
            java_script_enabled=False, viewport={"width": 390, "height": 844}
        )
        page = context.new_page()
        try:
            page.goto(f"{base_url}/{token}")
            page.locator("#q1-option-1").check()
            with page.expect_navigation(wait_until="load"):
                page.get_by_role("button", name="Send answers").click()

            assert page.locator("#q2-error").is_visible()
            assert page.locator("#q1-option-1").is_checked()
            assert page.locator("form").is_visible()
            page.locator("#q2-option-1").check()
            page.locator("#q2-option-2").check()
            with page.expect_navigation(wait_until="load"):
                page.get_by_role("button", name="Send answers").click()

            assert page.get_by_role("heading", name="Answer stored").is_visible()
            assert page.locator("input").count() == 0
            assert page.get_by_text("rice", exact=True).is_visible()
            assert page.get_by_text("salad", exact=True).is_visible()
        finally:
            context.close()


def test_other_unicode_counter_and_comment_progress_at_320px(
    tmp_path, fake_clock: FakeClock, browser
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    token = rich_token(app.test_client())
    with running_server(app) as base_url:
        page = browser.new_page(viewport={"width": 320, "height": 700})
        try:
            page.goto(f"{base_url}/{token}", wait_until="networkidle")
            page.locator("#q1-comment").evaluate(
                "element => element.closest('details').open = true"
            )
            page.locator("#q1-comment").fill("Comment only")
            assert page.locator("[data-kl-progress-count]").text_content() == "0 of 2 answered"
            page.locator("#q1-option-other").check()
            text = "😀" * 2_000
            page.locator("#q1-other").fill(text)
            assert page.locator("#q1-other-count").text_content() == "2000 / 2000"
            assert page.locator("[data-kl-progress-count]").text_content() == "1 of 2 answered"
            page.locator("#q2-option-1").check()
            assert page.locator("[data-kl-progress-count]").text_content() == "2 of 2 answered"
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.get_by_role("button", name="Send answers").click()
            page.get_by_role("heading", name="Answer stored").wait_for()
            assert page.locator(".kl-other-answer p").text_content() == text
            assert page.locator(".kl-comment-answer p").text_content() == "Comment only"
        finally:
            page.close()


def test_no_javascript_other_error_preserves_text_and_succeeds_at_320px(
    tmp_path, fake_clock: FakeClock, browser
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    token = rich_token(app.test_client())
    with running_server(app) as base_url:
        context = browser.new_context(
            java_script_enabled=False, viewport={"width": 320, "height": 700}
        )
        page = context.new_page()
        try:
            page.goto(f"{base_url}/{token}")
            page.locator("#q1-option-other").focus()
            page.keyboard.press("Space")
            page.locator("#q1-comment").evaluate(
                "element => element.closest('details').open = true"
            )
            page.locator("#q1-comment").fill("<b>literal comment</b>")
            page.locator("#q2-option-1").check()
            with page.expect_navigation(wait_until="load"):
                page.get_by_role("button", name="Send answers").click()
            assert page.locator("#q1-other-error").is_visible()
            assert page.locator("#q1-option-other").is_checked()
            assert page.locator("#q1-comment").input_value() == "<b>literal comment</b>"
            assert page.locator("#q1-comment").evaluate(
                "element => element.closest('details').open"
            )
            assert page.locator("#q2-option-1").is_checked()
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.locator("#q1-other").fill("sparkling water")
            with page.expect_navigation(wait_until="load"):
                page.get_by_role("button", name="Send answers").click()
            assert page.get_by_role("heading", name="Answer stored").is_visible()
            assert page.locator(".kl-comment-answer p").text_content() == "<b>literal comment</b>"
        finally:
            context.close()


def test_htmx_413_preserves_form_allows_retry_and_has_no_csp_errors(
    tmp_path, fake_clock: FakeClock, browser
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    token = rich_token(app.test_client())
    with running_server(app) as base_url:
        page = browser.new_page(viewport={"width": 320, "height": 700})
        console_errors = collect_console_errors(page)
        try:
            page.goto(f"{base_url}/{token}", wait_until="networkidle")
            page.locator("#q1-option-other").check()
            oversized = "😀" * 50_000
            page.locator("#q1-other").fill(oversized)
            page.locator("#q1-comment").evaluate(
                "element => element.closest('details').open = true"
            )
            page.locator("#q1-comment").fill("Keep this comment")
            page.locator("#q2-option-1").check()
            pending = submit_answers(page)
            assert pending.status == 413
            page.locator("#answer-request-error").wait_for(state="visible")
            assert page.evaluate("document.activeElement.id") == "answer-request-error"
            assert page.locator("#q1-other").input_value() == oversized
            assert page.locator("#q1-comment").input_value() == "Keep this comment"
            assert page.locator("#q1-option-other").is_checked()
            assert page.locator("#q2-option-1").is_checked()
            page.locator("#q1-other").fill("short enough")
            retry = submit_answers(page)
            assert retry.status == 200
            page.get_by_role("heading", name="Answer stored").wait_for()
            assert page.locator(".kl-comment-answer p").text_content() == "Keep this comment"
            assert not csp_violations(console_errors)
        finally:
            page.close()
