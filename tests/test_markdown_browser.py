from __future__ import annotations

import copy
from urllib.parse import urlsplit

from tests.app_helpers import make_app, post_creation
from tests.browser_helpers import collect_console_errors, csp_violations, running_server
from tests.helpers import FakeClock
from tests.test_markdown_api import MARKDOWN_BODY


def test_markdown_code_keyboard_selection_no_javascript_and_same_origin_requests(
    tmp_path, fake_clock: FakeClock, browser
) -> None:
    body = copy.deepcopy(MARKDOWN_BODY)
    body["questions"][0]["answers"][0] = (
        "Delete **recursively**\n```sh onload=alert(1)\n"
        "cd /your-folder && rm -rf -- " + "x" * 300 + "\n```"
    )
    body["questions"][1]["answers"][1] += " ![tracker](https://evil.invalid/pixel)"
    app, _ = make_app(tmp_path, fake_clock)
    token = post_creation(app.test_client(), body=body).json["url"].rsplit("/", 1)[-1]
    with running_server(app) as base_url:
        context = browser.new_context(
            java_script_enabled=False, viewport={"width": 320, "height": 700}
        )
        page = context.new_page()
        requests = []
        console_errors = collect_console_errors(page)
        page.on("request", lambda request: requests.append(request.url))
        try:
            page.goto(f"{base_url}/{token}")
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            code = page.locator("#q1-option-1-description pre")
            assert code.evaluate("el => el.scrollWidth > el.clientWidth")
            assert page.locator("#q1-option-1").is_checked() is False
            code.select_text()
            assert page.locator("#q1-option-1").is_checked() is False
            page.evaluate("window.getSelection().removeAllRanges()")
            code.focus()
            before = code.evaluate("el => el.scrollLeft")
            for _ in range(8):
                page.keyboard.press("ArrowRight")
            page.wait_for_timeout(500)
            assert code.evaluate("el => el.scrollLeft") > before
            label = page.locator('label[for="q1-option-1"]')
            assert label.bounding_box()["height"] >= 44
            label.click()
            assert page.locator("#q1-option-1").is_checked()
            page.locator("#q2-option-1").check()
            with page.expect_navigation(wait_until="load"):
                page.get_by_role("button", name="Send answers").click()
            assert page.get_by_role("heading", name="Answer stored").is_visible()
            assert page.locator(".kl-selected-recommendation pre").is_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            expected_host = urlsplit(base_url).netloc
            assert all(urlsplit(url).netloc == expected_host for url in requests)
            assert not csp_violations(console_errors)
        finally:
            context.close()
