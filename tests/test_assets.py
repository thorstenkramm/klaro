from __future__ import annotations

import hashlib
import re
from importlib.resources import files
from urllib.parse import urlsplit

from tests.app_helpers import make_app, post_creation
from tests.browser_helpers import running_server
from tests.helpers import FakeClock

ASSETS = {
    "/static/vendor/uikit/uikit.min.css": "static/vendor/uikit/uikit.min.css",
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
    assert "markdown-it-py" in notices
    assert package.joinpath("licenses/markdown-it-py.txt").is_file()
    assert package.joinpath("licenses/mdurl.txt").is_file()


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
            paths = {urlsplit(url).path for url in requests}
            assert "/static/vendor/uikit/uikit.min.css" in paths
            assert "/static/vendor/htmx/htmx.min.js" in paths
            assert "/static/klaro/klaro.js" in paths
            assert "/static/vendor/uikit/uikit.min.js" not in paths
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
    assert html.count("/static/vendor/") == 2  # UIkit CSS and htmx; UIkit JS is not used


def test_pages_link_content_versioned_assets_that_browsers_may_cache(
    tmp_path, fake_clock: FakeClock
) -> None:
    app, _ = make_app(tmp_path, fake_clock)
    client = app.test_client()
    token = post_creation(client).json["url"].rsplit("/", 1)[-1]
    page = client.get(f"/{token}", headers={"Accept": "text/html"})
    links = dict(
        re.findall(r'(?:href|src)="(/static/[^"?]+)\?v=([0-9a-f]+)"', page.get_data(as_text=True))
    )
    package = files("klaro")

    assert set(links) == {
        "/static/vendor/uikit/uikit.min.css",
        "/static/klaro/klaro.css",
        "/static/vendor/htmx/htmx.min.js",
        "/static/klaro/klaro.js",
    }
    for path, version in links.items():
        content = package.joinpath(path.removeprefix("/")).read_bytes()
        assert version == hashlib.sha256(content).hexdigest()[:16]
        current = client.get(f"{path}?v={version}")
        stale = client.get(f"{path}?v=0000000000000000")
        unversioned = client.get(path)
        assert current.headers["Cache-Control"] == "public, max-age=31536000, immutable"
        assert stale.headers["Cache-Control"] == "no-cache"
        assert unversioned.headers["Cache-Control"] == "no-cache"
        assert current.headers["X-Content-Type-Options"] == "nosniff"
    assert page.headers["Cache-Control"] == "no-store"
    assert client.get("/static/missing.js").headers["Cache-Control"] == "no-store"


def test_stylesheet_keeps_every_colour_in_custom_properties() -> None:
    css = files("klaro").joinpath("static/klaro/klaro.css").read_text()
    root_start = css.index(":root {")
    root_end = css.index("\n}\n", root_start)
    outside_root = css[:root_start] + css[root_end:]

    assert re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(", outside_root) == []
    assert "!important" not in css
