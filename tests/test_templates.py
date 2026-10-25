from __future__ import annotations

from bs4 import BeautifulSoup

from tests.app_helpers import make_app, post_creation
from tests.helpers import FakeClock


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
    assert all(fieldset["aria-required"] == "true" for fieldset in soup.select("fieldset"))
    for control in soup.select("input"):
        label = soup.select_one(f'label[for="{control["id"]}"]')
        assert label is not None
        assert label.get_text(strip=True) == control["value"].strip()
    form = soup.select_one("form")
    assert form["method"] == "post"
    assert form["hx-post"] == f"/{token}"
    assert form["hx-target"] == "#questionnaire-response"
    assert soup.select_one('meta[name="htmx-config"]') is not None


def test_validation_rerenders_errors_and_entered_values(tmp_path, fake_clock: FakeClock) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = created_token(client)

    response = client.post(f"/{token}", data={"q1": "beer"})
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

    response = client.post(f"/{token}", data={"q1": "beer"}, headers={"HX-Request": "true"})

    assert response.status_code == 422
    assert response.text.startswith('<section id="questionnaire-response"')
    assert "<html" not in response.text
    assert 'id="q2-error"' in response.text


def test_answered_page_is_read_only(tmp_path, fake_clock: FakeClock) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = created_token(client)
    response = client.post(f"/{token}", data={"q1": "beer", "q2": ["rice", "salad"]})

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
