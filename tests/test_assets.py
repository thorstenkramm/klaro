from __future__ import annotations

from importlib.resources import files
from urllib.parse import urlsplit

from tests.app_helpers import make_app, post_creation
from tests.browser_helpers import running_server
from tests.helpers import FakeClock

ASSETS = {
    "/static/vendor/uikit/uikit.min.css": "static/vendor/uikit/uikit.min.css",
    "/static/vendor/uikit/uikit.min.js": "static/vendor/uikit/uikit.min.js",
    "/static/vendor/htmx/htmx.min.js": "static/vendor/htmx/htmx.min.js",
    "/static/vendor/uikit/LICENSE.md": "static/vendor/uikit/LICENSE.md",
    "/static/vendor/htmx/LICENSE": "static/vendor/htmx/LICENSE",
}


def test_vendor_assets_and_notices_are_package_resources() -> None:
    package = files("klaro")
    for resource in ASSETS.values():
        assert package.joinpath(resource).is_file()
    notices = package.joinpath("THIRD_PARTY_NOTICES.md").read_text()
    assert "UIkit 3.25.27" in notices
    assert "HTMX 2.0.11" in notices
    assert "MIT" in notices
    assert "0BSD" in notices


def test_static_routes_serve_exact_packaged_files(tmp_path, fake_clock: FakeClock) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    package = files("klaro")

    for route, resource in ASSETS.items():
        response = client.get(route)
        assert response.status_code == 200
        assert response.data == package.joinpath(resource).read_bytes()


def test_browser_loads_only_same_origin_assets(tmp_path, fake_clock: FakeClock, browser) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    token = post_creation(app.test_client()).json["url"].rsplit("/", 1)[-1]

    with running_server(app) as base_url:
        page = browser.new_page(viewport={"width": 390, "height": 844})
        requests = []
        failures = []
        page.on("request", lambda request: requests.append(request.url))
        page.on("requestfailed", lambda request: failures.append(request.url))
        try:
            page.goto(f"{base_url}/{token}", wait_until="networkidle")
            assert page.locator("h1").is_visible()
            assert page.evaluate("typeof window.htmx") in {"object", "function"}
            assert page.evaluate("document.styleSheets.length") >= 1
            assert any(url.endswith("/static/vendor/uikit/uikit.min.css") for url in requests)
            assert any(url.endswith("/static/vendor/uikit/uikit.min.js") for url in requests)
            assert any(url.endswith("/static/vendor/htmx/htmx.min.js") for url in requests)
            expected_host = urlsplit(base_url).netloc
            third_party = [url for url in requests if urlsplit(url).netloc != expected_host]
            assert third_party == []
            assert failures == []
        finally:
            page.close()


def test_html_has_no_external_asset_urls(tmp_path, fake_clock: FakeClock) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    token = post_creation(app.test_client()).json["url"].rsplit("/", 1)[-1]

    response = app.test_client().get(f"/{token}", headers={"Accept": "text/html"})
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "https://cdn" not in html
    assert "http://" not in html
    assert "https://" not in html
    assert html.count("/static/vendor/") == 3
