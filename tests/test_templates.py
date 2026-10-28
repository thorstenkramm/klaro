from __future__ import annotations

from bs4 import BeautifulSoup

from tests.app_helpers import make_app, post_creation
from tests.helpers import FakeClock
from tests.test_text_answers import rich_token


def created_token(client) -> str:
    return post_creation(client).json["url"].rsplit("/", 1)[-1]


def test_semantic_mobile_form_controls_and_labels(tmp_path, fake_clock: FakeClock) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = created_token(client)

    response = client.get(f"/{token}", headers={"Accept": "text/html"})
    soup = BeautifulSoup(response.text, "html.parser")

    assert soup.select_one('meta[name="viewport"]') is not None
    assert len(soup.select("fieldset")) == 2
    assert [legend.get_text(strip=True) for legend in soup.select("legend")] == [
        "1. Drink?",
        "2. Sides?",
    ]
    assert len(soup.select('input[type="radio"]')) == 2
    assert len(soup.select('input[type="checkbox"]')) == 2
    assert all(control.has_attr("required") for control in soup.select('input[type="radio"]'))
    # ARIA allows a required state only on radio groups; checkbox groups state it in the hint.
    radio_group, checkbox_group = soup.select("fieldset")
    assert radio_group["role"] == "radiogroup"
    assert radio_group["aria-required"] == "true"
    assert not checkbox_group.has_attr("role")
    assert not checkbox_group.has_attr("aria-required")
    assert soup.select_one("#q2-hint").get_text(strip=True) == "Select at least one answer."
    for control in soup.select("input"):
        label = soup.select_one(f'label[for="{control["id"]}"]')
        assert label is not None
        options = {"q1": ["beer", "water"], "q2": ["rice", "salad"]}
        assert label.get_text(strip=True) == options[control["name"]][int(control["value"]) - 1]
    form = soup.select_one("form")
    assert form["method"] == "post"
    assert form["hx-post"] == f"/{token}"
    assert form["hx-target"] == "#questionnaire-response"
    assert soup.select_one('meta[name="htmx-config"]') is not None


def test_validation_rerenders_errors_and_entered_values(tmp_path, fake_clock: FakeClock) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = created_token(client)

    response = client.post(f"/{token}", data={"q1": "1"})
    soup = BeautifulSoup(response.text, "html.parser")

    assert response.status_code == 422
    assert soup.select_one("#q2-error").get_text(strip=True) == "Select at least one answer."
    assert soup.select_one("#q1-option-1").has_attr("checked")
    assert soup.select_one("form") is not None
    assert app.extensions["klaro"].store.read(token).status == "awaiting_answer"


def test_htmx_validation_response_is_only_the_swap_fragment(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = created_token(client)

    response = client.post(f"/{token}", data={"q1": "1"}, headers={"HX-Request": "true"})

    assert response.status_code == 422
    assert response.text.startswith('<section id="questionnaire-response"')
    assert "<html" not in response.text
    assert 'id="q2-error"' in response.text


def test_answered_page_is_read_only(tmp_path, fake_clock: FakeClock) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = created_token(client)
    response = client.post(f"/{token}", data={"q1": "1", "q2": ["1", "2"]})

    assert response.status_code == 200
    soup = BeautifulSoup(response.text, "html.parser")
    assert soup.select_one("h2").get_text(strip=True) == "Answer stored"
    assert soup.select_one("form") is None
    assert soup.select("input") == []
    assert "beer" in response.text
    assert "rice" in response.text
    assert "salad" in response.text

    later = client.get(f"/{token}", headers={"Accept": "text/html"})
    assert "Answer stored" in later.text
    assert BeautifulSoup(later.text, "html.parser").select("input") == []


def test_other_and_comment_controls_repopulate_validation_errors(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = rich_token(client)
    response = client.post(
        f"/{token}",
        data={
            "q1": "other",
            "q1-other": ["<script>not code</script>", "repeated"],
            "q1-comment": "<b>literal note</b>",
            "q2": "1",
        },
    )
    soup = BeautifulSoup(response.text, "html.parser")
    assert response.status_code == 422
    other = soup.select_one("#q1-other")
    comment = soup.select_one("#q1-comment")
    assert other.text == "<script>not code</script>"
    assert other["aria-invalid"] == "true"
    assert "q1-other-error" in other["aria-describedby"]
    assert soup.select_one("#q1-option-other").has_attr("checked")
    assert comment.text == "<b>literal note</b>"
    assert comment.find_parent("details").has_attr("open")
    assert soup.select_one("[data-kl-progress-count]").text == "2 of 2 answered"
    assert soup.select("textarea[maxlength]") == []
    assert soup.select_one("script:not([src])") is None


def test_comment_alone_does_not_count_as_an_answer(tmp_path, fake_clock: FakeClock) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = rich_token(client)
    response = client.post(f"/{token}", data={"q2": "1", "q1-comment": "not a selection"})
    assert response.status_code == 422
    assert "1 of 2 answered" in response.text


def test_answered_other_and_comment_are_escaped_and_preserve_lines(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = rich_token(client)
    response = client.post(
        f"/{token}",
        data={
            "q1": "other",
            "q1-other": "<script>literal</script>\n**not markdown**",
            "q1-comment": "<b>literal</b>\nsecond line",
            "q2": ["1", "other"],
            "q2-other": "corn",
        },
    )
    soup = BeautifulSoup(response.text, "html.parser")
    assert response.status_code == 200
    assert soup.select_one(".kl-other-answer p").text == (
        "<script>literal</script>\n**not markdown**"
    )
    assert soup.select_one(".kl-comment-answer p").text == "<b>literal</b>\nsecond line"
    assert soup.select_one("script:not([src])") is None
    assert "<script>literal</script>" not in response.text
    assert "&lt;script&gt;literal&lt;/script&gt;" in response.text
    assert soup.select_one(".kl-comment-answer h4").text == "Your comment"
