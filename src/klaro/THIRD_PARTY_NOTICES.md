# Third-party notices

Klaro serves the following pinned distributions from its own `/static/` routes. No runtime CDN downloads are used.

## UIkit 3.25.27

- Upstream: https://getuikit.com/
- npm source: https://registry.npmjs.org/uikit/-/uikit-3.25.27.tgz
- npm tarball SHA-1: `30f820d9f3a3d1207a55023188c4b0e24badaf74`
- Distributed files: `static/vendor/uikit/uikit.min.css` (CSS only; UIkit's JavaScript is not used)
- License: MIT; full notice in `static/vendor/uikit/LICENSE.md`

## HTMX 2.0.11

- Upstream: https://htmx.org/
- npm source: https://registry.npmjs.org/htmx.org/-/htmx.org-2.0.11.tgz
- npm tarball SHA-1: `a85363c4c5af94cd634df04c4b83d06dd0e91aa7`
- Distributed file: `static/vendor/htmx/htmx.min.js`
- License: BSD Zero Clause (0BSD); full notice in `static/vendor/htmx/LICENSE`

## markdown-it-py 4.x

- Upstream: https://github.com/executablebooks/markdown-it-py
- Python dependency declared as `markdown-it-py>=3.0,<5`; the lockfile selects the exact build
- Used only for server-side tokenization; no browser JavaScript or external assets are distributed
- License: MIT; full markdown-it-py and upstream markdown-it notices in `licenses/markdown-it-py.txt`

## mdurl 0.1.x

- Upstream: https://github.com/executablebooks/mdurl
- Transitive dependency of markdown-it-py; the lockfile selects the exact build
- License: MIT; full notice, including the Node.js URL parser notice, in `licenses/mdurl.txt`
