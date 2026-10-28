from __future__ import annotations

from bs4 import BeautifulSoup

from tests.app_helpers import make_app, post_creation
from tests.browser_helpers import (
    collect_console_errors,
    csp_violations,
    running_server,
    submit_answers,
)
from tests.helpers import FakeClock
from tests.test_recommendations import REC_BODY, recommendation_token


def test_initial_recommendations_are_accessible_guidance_without_preselection(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    questioner = "<script>Questioner</script>"
    response = post_creation(client, body=REC_BODY, questioner=questioner)
    token = response.json["url"].rsplit("/", 1)[-1]
    soup = BeautifulSoup(
        client.get(f"/{token}", headers={"Accept": "text/html"}).text, "html.parser"
    )
    assert soup.select("input:checked") == []
    assert soup.select_one("[data-kl-progress-count]").text == "0 of 2 answered"
    assert len(soup.select(".kl-option--recommended")) == 3
    assert (
        soup.select_one('label[for="q1-option-1"]').get_text(" ", strip=True) == "Recommended beer"
    )
    assert (
        soup.select_one('label[for="q1-option-4"]').get_text(" ", strip=True) == "Recommended tea"
    )
    assert (
        soup.select_one('label[for="q2-option-2"]').get_text(" ", strip=True) == "Recommended salad"
    )
    assert all(input.has_attr("required") for input in soup.select('input[type="radio"]'))
    footer = soup.select_one(".kl-recommendation-note")
    assert footer.get_text() == (
        "Recommendations come from <script>Questioner</script>. Nothing is preselected."
    )
    assert footer.find("script") is None
    assert "★" not in response.text
    assert "recommended choices" not in response.text


def test_read_only_distinguishes_selected_and_not_chosen_recommendations(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = recommendation_token(client)
    response = client.post(f"/{token}", data={"q1": "1", "q2": "1"})
    soup = BeautifulSoup(response.text, "html.parser")
    answers = soup.select(".kl-answer")
    assert answers[0].select_one(".kl-selected-recommendation").get_text(" ", strip=True) == (
        "beer Recommended"
    )
    assert [item.get_text(" ", strip=True) for item in answers[0].select(".kl-not-chosen")] == [
        "Recommended tea not chosen"
    ]
    assert answers[0].select_one(".kl-not-chosen-list").get_text(" ", strip=True).count("beer") == 0
    assert answers[1].select(".kl-selected-recommendation") == []
    assert [item.get_text(" ", strip=True) for item in answers[1].select(".kl-not-chosen")] == [
        "Recommended salad not chosen"
    ]
    public = client.get(f"/{token}", headers={"Accept": "application/json"}).json
    assert public["questions"][0]["answered"] == ["beer"]
    assert public["questions"][1]["answered"] == ["rice"]


def test_other_answer_does_not_hide_or_impersonate_recommendations(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = recommendation_token(client)
    response = client.post(
        f"/{token}",
        data={"q1": "other", "q1-other": "tea", "q1-comment": "my choice", "q2": "2"},
    )
    soup = BeautifulSoup(response.text, "html.parser")
    answers = soup.select(".kl-answer")
    assert answers[0].select_one(".kl-other-answer p").text == "tea"
    assert [item.get_text(" ", strip=True) for item in answers[0].select(".kl-not-chosen")] == [
        "Recommended beer not chosen",
        "Recommended tea not chosen",
    ]
    assert answers[1].select_one(".kl-selected-recommendation").get_text(" ", strip=True) == (
        "salad Recommended"
    )
    assert answers[1].select(".kl-not-chosen") == []
    public = client.get(f"/{token}", headers={"Accept": "application/json"}).json
    assert public["questions"][0]["answered"] == []
    assert public["questions"][0]["other"] == "tea"
    assert public["questions"][1]["answered"] == ["salad"]


def long_recommendation_body():
    return {
        "questions": [
            {
                **REC_BODY["questions"][0],
                "answers": [
                    "A very long recommended drink label " + "x" * 160,
                    "water",
                    "wine",
                    "tea",
                ],
            },
            REC_BODY["questions"][1],
        ]
    }


def test_recommendations_mobile_keyboard_htmx_correction_and_csp(
    tmp_path, fake_clock: FakeClock, browser
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    token = (
        post_creation(app.test_client(), body=long_recommendation_body())
        .json["url"]
        .rsplit("/", 1)[-1]
    )
    with running_server(app) as base_url:
        page = browser.new_page(viewport={"width": 320, "height": 700})
        console_errors = collect_console_errors(page)
        try:
            page.goto(f"{base_url}/{token}", wait_until="networkidle")
            assert page.locator("input:checked").count() == 0
            assert page.locator("[data-kl-progress-count]").text_content() == "0 of 2 answered"
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.locator("#q1-option-1").focus()
            assert (
                page.locator("#q1-option-1").evaluate("el => getComputedStyle(el).outlineStyle")
                != "none"
            )
            page.keyboard.press("Space")
            assert page.locator("#q1-option-1").is_checked()
            page.locator("#q1-comment").evaluate("el => el.closest('details').open = true")
            page.locator("#q1-comment").fill("Keep this")
            pending = submit_answers(page)
            assert pending.status == 422
            page.locator("#q2-error").wait_for()
            assert page.locator("#q1-option-1").is_checked()
            assert page.locator("#q1-comment").input_value() == "Keep this"
            assert (
                page.locator("#q1-option-1").evaluate(
                    "el => getComputedStyle(el.closest('.kl-option')).borderColor"
                )
                == "rgb(234, 88, 12)"
            )
            page.locator("#q1-option-other").check()
            page.locator("#q1-other").fill("My own answer")
            page.locator("#q2-option-2").check()
            success = submit_answers(page)
            assert success.status == 200
            page.get_by_role("heading", name="Answer stored").wait_for()
            assert page.locator(".kl-other-answer p").text_content() == "My own answer"
            assert page.locator(".kl-comment-answer p").text_content() == "Keep this"
            assert page.locator(".kl-answer").nth(0).locator(".kl-not-chosen").count() == 2
            assert not csp_violations(console_errors)
        finally:
            page.close()


def test_recommendations_no_javascript_keyboard_and_correction(
    tmp_path, fake_clock: FakeClock, browser
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    token = (
        post_creation(app.test_client(), body=long_recommendation_body())
        .json["url"]
        .rsplit("/", 1)[-1]
    )
    with running_server(app) as base_url:
        context = browser.new_context(
            java_script_enabled=False, viewport={"width": 320, "height": 700}
        )
        page = context.new_page()
        try:
            page.goto(f"{base_url}/{token}")
            assert page.locator("input:checked").count() == 0
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.locator("#q1-option-1").focus()
            page.keyboard.press("Space")
            with page.expect_navigation(wait_until="load"):
                page.get_by_role("button", name="Send answers").click()
            assert page.locator("#q2-error").is_visible()
            assert page.locator("#q1-option-1").is_checked()
            page.locator("#q2-option-2").focus()
            page.keyboard.press("Space")
            with page.expect_navigation(wait_until="load"):
                page.get_by_role("button", name="Send answers").click()
            assert page.get_by_role("heading", name="Answer stored").is_visible()
            assert page.locator(".kl-selected-recommendation").count() == 2
        finally:
            context.close()
