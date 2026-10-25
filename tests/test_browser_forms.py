from __future__ import annotations

from tests.app_helpers import make_app, post_creation
from tests.browser_helpers import running_server
from tests.helpers import FakeClock


def token_for(app) -> str:
    return post_creation(app.test_client()).json["url"].rsplit("/", 1)[-1]


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
            with page.expect_response(
                lambda response: response.request.method == "POST"
            ) as pending:
                page.get_by_role("button", name="Send answers").click()
            validation = pending.value
            assert validation.status == 422
            assert "<html" not in validation.text()

            page.locator("#q2-error").wait_for()
            assert page.locator("#q1-option-1").is_checked()
            assert page.locator("form").is_visible()
            page.locator("#q2-option-1").check()
            with page.expect_response(
                lambda response: response.request.method == "POST"
            ) as pending_success:
                page.get_by_role("button", name="Send answers").click()
            success = pending_success.value
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
