# Klaro – agent instructions

Klaro sends a questionnaire to a Pushover recipient, lets them answer once on a mobile-friendly page, and returns the
answer to the questioner by polling or server-sent events. Python 3.11+, Flask, Jinja, gevent/Gunicorn, JSON files on
disk, locally served UIkit CSS and htmx. `README.md` is the user and operations manual; `openspec/specs/` is the
behaviour contract.

These rules capture decisions that are not obvious from the code, including the results of the 2026-10 code review
(`tmp/code-review-2026-10-27.md`, git-ignored).

## Non-negotiable design decisions

- **The weak authentication is intended.** The secret capability URL (256-bit token) is the only credential, and
  `X-Questioner` is an unauthenticated display and filter label. Never add user accounts, logins, API keys, or
  per-user credentials, and never describe the label as identity.
- **Exactly one instance with one gevent worker** (`workers = 1`). Per-token locks, SSE wake-ups, and the creation
  rate limit and backoff live in that process. Never "fix" this by adding workers or instances.
- **Klaro is served from the root of its own host name.** `klaro.public_address` must not contain a path; sub-path
  hosting is not planned.
- **Answer submission is browser-only** (HTML pages and HTMX fragments). Every other route speaks the JSON
  `{"error": {...}}` contract, including unexpected `500` errors for non-browser clients.
- **No JavaScript build step and no CDN.** Native forms must work without JavaScript; `klaro.js` only enhances them.
  Same-origin CSP: no inline scripts, styles, or event handlers.
- **Storage schema 4 needs a fresh data directory** when its format changes; there is no migration. Unreadable records
  are never served, are logged without their token, and are deleted after their lifetime.

## Where things live

| Concern | Module |
| --- | --- |
| App factory, routes, errors, security headers | `app.py`, `routes.py`, `responses.py`, `runtime.py` |
| Every size and count limit | `limits.py` (the only place for such literals; a test enforces it) |
| Input validation | `models.py` (questionnaires), `answers.py` (form answers), `parsing.py` (bodies), `validation.py` (headers) |
| Records and persistence | `records.py` (encoding, projections, `InvalidRecord`), `filestore.py` (I/O, locks, transitions) |
| Live updates and cleanup | `sse.py`, `subscribers.py`, `scheduler.py` |
| Abuse controls and client identity | `abuse.py` (IPv4 address or IPv6 /64), `client_ip.py` (trusted proxies) |
| Markdown rendering | `markdown.py` (restricted subset, linear-time, cached) |
| Front end | `templates/`, `static/klaro/klaro.css` (UIkit override layer), `static/klaro/klaro.js` (ES module) |
| Vendored assets | `static/vendor/` (UIkit CSS, htmx); never edit, update with `THIRD_PARTY_NOTICES.md` |

## Workflow

- **Behaviour changes go through OpenSpec**: `/opsx-propose`, `/opsx-apply`, `/opsx-archive`. Do not edit
  `openspec/specs/*` directly. Pure refactoring, tooling, or tests that keep specified behaviour need no change.
- Every spec scenario must map to executable tests in `tests/scenario-coverage.md`. While a change is implemented but
  not yet archived, list it in `IMPLEMENTED_DELTAS` in `tests/test_verification_matrix.py`.
- Never commit, push, or stage files unless explicitly asked. Treat untracked or unfamiliar files as the user's work.
- Use `uv` for Python (`uv run`, `uv add --dev`), never bare `pip`. Keep `uv.lock` and `package-lock.json` in sync.

## Definition of done

Run the gates CI runs (`.github/workflows/ci.yml`) and fix every finding rather than relaxing a threshold:

```shell
uv run ruff check src tests
uv run ruff format --check src tests
uv run flake8
uv run mypy
uv run pytest --cov
npx --yes jscpd@5.4.2
npm run lint:js
openspec validate --all --strict
trivy fs --config trivy.yaml .
```

- `pytest --cov` enforces 94 % branch coverage; it includes Playwright browser and axe accessibility tests
  (`uv run playwright install chromium` once).
- Thresholds: flake8 complexity 10, jscpd 3 %, strict mypy, Ruff rules in `pyproject.toml`. Inline `noqa` only with a
  stated reason, as in `parsing.py` and `markdown.py`.
- Update `README.md` when behaviour, configuration, or operations change; several tests check its examples and numbers.

## Dos

1. **Bound every resource an unauthenticated request can allocate**: memory, CPU, file handles, and log volume. Ask
   "what if this runs a million times?" for every dictionary, cache, and loop keyed by request data. Per-token state
   must be released when no longer held.
2. **Define each rule and limit exactly once** and reuse it everywhere: Python, templates (`limits` Jinja global,
   `data-kl-max`), and JavaScript. Decode stored data through the same validators as input.
3. **Test hostile input with properties, not only examples**: Hypothesis for parsers, Markdown, and form submissions;
   performance budgets for worst cases (`tests/test_resource_bounds.py`).
4. **Keep functions small and importable**: routes in the Blueprint, pure validators separate from I/O, `StrEnum` or
   `Literal` states, `@dataclass(frozen=True, slots=True)` value objects.
5. **Let the type checker work**: `NoReturn` for always-raising helpers, `Mapping`/`Sequence` parameters, no `Any`
   leaking out of validation.
6. **Treat accessibility as a tested contract**: focus moves after every HTMX swap, results are announced through the
   persistent live region, alerts use `role="alert"`, and the axe tests stay clean (WCAG 2.x A/AA, 4.5:1 contrast).
7. **Synchronise on events in tests**: inject `FakeClock`, wait on transitions or conditions. The only accepted sleep is
   the readiness poll for an external server process (`tests/process_helpers.py`).
8. **Prove a new test can fail** (break the code or remove the attribute once) before trusting it, and prefer shared
   helpers (`tests/browser_helpers.py`, `tests/response_helpers.py`) over copied setup.

## Don'ts

1. **Don't allocate per-key state before validating the key**, and don't keep "allocate forever" structures in the
   long-lived worker.
2. **Don't re-implement validation in a second layer** or keep compatibility shims and dead code "just for tests";
   tests exercise public contracts and projections.
3. **Don't write quadratic algorithms over user-controlled text** (nested rescans, repeated `str.replace`, backtracking
   regular expressions). Rendering runs on the single worker.
4. **Don't put secrets or tokens in logs, error bodies, or answer data.** Logging goes through the redacting filter;
   never mutate logged exception objects.
5. **Don't apply response headers blindly**: questionnaire responses are `no-store`; static assets are linked through
   `asset_url()` with a content hash and cached for a year.
6. **Don't add colour literals or `!important` to `klaro.css`**: every colour is a `--kl-*` custom property; UIkit is
   themed by this override layer only, with no Less/Sass build and no UIkit JavaScript.
7. **Don't pin anything loosely in CI**: GitHub Actions by full commit SHA with a version comment, tools by exact
   version, Docker images by digest.

## Reviewing changes

Use the `reviewer` subagent (`.opencode/agents/reviewer.md`) for reviews. Beyond correctness, every review covers:

- resource cost per anonymous request, and behaviour on the single worker;
- deployment and topology assumptions (single worker, root hosting, trusted proxies, IPv6 /64 grouping);
- hostile-input robustness: no client input may produce a `500`;
- static typing, tests that would fail without the change, and mutation-relevant gaps;
- accessibility (WCAG 2.2 AA), keyboard use, no-JavaScript use, and CSP compliance;
- supply chain: dependency and licence changes, vendored assets, pins, `THIRD_PARTY_NOTICES.md`;
- operability: logging of degraded paths without secrets, and documented recovery;
- the thresholds above: duplication, complexity, coverage, and lint rules.
