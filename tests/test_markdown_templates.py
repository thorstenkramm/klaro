from __future__ import annotations

from bs4 import BeautifulSoup

from tests.app_helpers import make_app, post_creation
from tests.helpers import FakeClock
from tests.test_markdown_api import MARKDOWN_BODY, markdown_token


def test_active_markdown_has_safe_label_heads_and_associated_descriptions(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = (
        post_creation(client, body=MARKDOWN_BODY, questioner="<b>Questioner</b>")
        .json["url"]
        .rsplit("/", 1)[-1]
    )
    response = client.get(f"/{token}", headers={"Accept": "text/html"})
    soup = BeautifulSoup(response.text, "html.parser")
    legend = soup.select_one("legend")
    assert legend.strong.text == "clean up"
    assert legend.code.text == "/your-folder"
    assert soup.select_one(".kl-head__title").find("b") is None
    assert "<b>Questioner</b>" in soup.select_one(".kl-head__title").text

    first_label = soup.select_one('label[for="q1-option-1"]')
    assert first_label.strong.text == "recursively"
    assert first_label.find(["p", "pre"]) is None
    first_input = soup.select_one("#q1-option-1")
    assert first_input["aria-describedby"] == "q1-option-1-description"
    description = soup.select_one("#q1-option-1-description")
    assert description.find_parent("label") is None
    assert description.pre["tabindex"] == "0"
    assert description.pre["aria-label"] == "Code block"
    assert description.code.text == "cd /your-folder\nrm -rf\n"
    second_label = soup.select_one('label[for="q1-option-2"]')
    assert second_label.em.text == "loop"
    assert second_label.get_text(" ", strip=True) == "Recommended Delete with a loop"
    literal_link = soup.select_one('label[for="q2-option-2"]')
    assert "[literal](https://example.com)" in literal_link.text
    assert literal_link.find("a") is None
    assert soup.select("[style], [onclick], [onload], script:not([src])") == []


def test_selected_and_not_chosen_options_retain_rich_formatting(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = markdown_token(client)
    response = client.post(f"/{token}", data={"q1": "1", "q2": "1"})
    soup = BeautifulSoup(response.text, "html.parser")
    selected = soup.select_one(".kl-selected-recommendation")
    assert selected.find("strong").text == "recursively"
    assert selected.find("pre").code.text == "cd /your-folder\nrm -rf\n"
    assert selected.find("pre")["tabindex"] == "0"
    not_chosen = soup.select_one(".kl-not-chosen")
    assert not_chosen.find("em").text == "loop"
    assert "for file in *.png" in not_chosen.find("pre").text
    assert not_chosen.find("a") is None
    public = client.get(f"/{token}", headers={"Accept": "application/json"}).json
    assert public["questions"][0]["answers"] == MARKDOWN_BODY["questions"][0]["answers"]
    assert public["questions"][0]["answered"] == [MARKDOWN_BODY["questions"][0]["answers"][0]]


def test_other_comment_and_questioner_never_use_markdown_renderer(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = markdown_token(client)
    response = client.post(
        f"/{token}",
        data={
            "q1": "other",
            "q1-other": "**literal other** <script>x</script>",
            "q1-comment": "`literal comment`\n**still literal**",
            "q2": "1",
        },
    )
    soup = BeautifulSoup(response.text, "html.parser")
    assert soup.select_one(".kl-other-answer p").text == "**literal other** <script>x</script>"
    assert soup.select_one(".kl-other-answer").find(["strong", "code", "script"]) is None
    assert soup.select_one(".kl-comment-answer p").text == "`literal comment`\n**still literal**"
    assert soup.select_one(".kl-comment-answer").find(["strong", "code"]) is None
    assert soup.select_one("script:not([src])") is None
