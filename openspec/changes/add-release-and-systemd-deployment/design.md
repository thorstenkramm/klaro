# Design

## Context

See proposal.md for motivation. Feedback 02 supersedes the original multi-asset release and uv-tool installation
design. The current implementation already contains metadata-based version reporting, reusable CI, a release
workflow, deployment examples, and tests. It still builds wheels/constraints as separate assets and assumes an
installation under `/opt/klaro/tools`; those parts must be revised, not treated as completed work.

The Python CLI validates TOML and execs Gunicorn with one worker. `setup.py` embeds `uv.lock` during wheel builds.
Existing tests cover installed distributions, README operation blocks, and effective OpenSpec scenarios. The new
Linux tests currently skip locally and have not established a verified systemd exposure baseline.

## Goals / Non-Goals

**Goals:** one download, automatic locked runtime setup, a root-owned application tree, one shared startup path,
and publication of the exact deployment archive exercised by CI.

**Non-Goals:** offline bundles, bundled interpreters, PyPI publication, accounts, multiple instances, automatic
upgrades, or a release upgrade/rollback tutorial. Existing storage-format safeguards remain applicable.

## Decisions

### 1. Derive package versions from tags in a staging tree

Keep `project.version = "0.0.0.dev0"` and corresponding root package metadata in the source lockfile. Refactor the
release checker to validate a `v`-prefixed PEP 440 version rather than compare it with the placeholder. Use the
canonical version representation for archive and package metadata; ordinary tags such as `v0.1.0` remain unchanged.
Keep the original tag for GitHub operations. Runtime version reporting continues through installed metadata.

Prepare a temporary release project, inject its version, and update only the root package's lock metadata. Verify
that third-party versions, sources, and hashes are unchanged and that uv accepts the resulting lock as current.
Never resolve to newer dependencies simply to stamp a release. Keep the checkout unchanged. This replaces both
manual version bumps and setuptools-scm; the tag alone is sufficient to request a release.

### 2. One deployment archive with a fixed layout

Add a tested release builder that copies an explicit allowlist into a staging directory:

```text
bin/klaro
wheelhouse/klaro-<version>-py3-none-any.whl
requirements.txt
pyproject.toml
uv.lock
setup.py
MANIFEST.in
README.md
LICENSE
src/klaro/...
klaro.example.toml
klaro.service
Caddyfile
```

Include package assets, licence notices, and all build inputs needed for a non-editable install. Map the shipped
deployment examples into the archive root and preserve the launcher's executable mode. Exclude development caches,
repository metadata, `tmp/`, and secrets. Archive members must be relative paths with no escaping symlinks or `..`.
Name the result `klaro-<version>.tar.gz`; this is a deployment bundle, not the ordinary source distribution, even
though both use tar.gz. Keep their build output directories separate.

The archive is the sole uploaded deployment asset. GitHub's automatic source links and server-side attestation
records are separate platform features, not additional files operators must download. Internal CI artifacts may
carry digest/provenance metadata; do not require a separate public checksum file for installation.

### 3. Shared launcher with writable state outside the application

Create a small executable shell launcher at `deploy/bin/klaro`, packaged as `bin/klaro`. It locates the project
relative to itself and uses `/usr/local/bin/uv`, independent of the calling shell's PATH. Set explicit paths:

- project environment: `/var/lib/klaro/venv`;
- uv cache: `/var/lib/klaro/cache`;
- managed Python downloads: `/var/lib/klaro/python`;
- configuration: `/etc/klaro/klaro.toml`;
- questionnaire data: `/var/lib/klaro/data`.

Build the application wheel in CI and include it inside the deployment archive. A read-only-source experiment
confirmed that even `uv sync --no-editable` invokes setuptools in place and fails creating `src/klaro.egg-info`.
The user approved a bundled prebuilt wheel to avoid server-side builds. Export hashed runtime requirements from
the staged lock and append the bundled wheel's relative path and SHA-256 digest. Verify this export against the lock
in CI. The launcher creates a Python 3.12 environment with `uv venv` when missing, then uses `uv pip sync` with
`--require-hashes --only-binary :all:` and execs that environment's Python CLI. No package builds run on the server.
The final process is the existing launcher/Gunicorn, not a long-lived uv supervisor. Hash failures stop startup.
Prevent bytecode or build output writes to `/opt/klaro`; test with that tree actually read-only to the service user.
Initial interpreter/dependency downloads are allowed; failures produce nonzero startup with useful diagnostics.

No `uv tool install` step or service-writable application directory is necessary. Runtime code in the environment is
service-owned, an intentional consequence of unprivileged automatic setup; the release sources remain root-owned.

### 4. Account, configuration, and systemd

Use the feedback's persistent `useradd` account with `/var/lib/klaro` as home and a nologin shell. Retire the redundant
sysusers file and its tests during implementation. The sample TOML contains a clearly invalid token placeholder,
root-host public URL, loopback listen address, data directory, and trusted loopback proxy configuration.

Install application files as root, configuration as `root:klaro` mode `0640`, and state directories as `klaro`
mode `0700`. Link `/opt/klaro/klaro.service` into `/etc/systemd/system/`. Set `ExecStart=/opt/klaro/bin/klaro`
without duplicating configuration flags. Preserve restart rate limiting, graceful shutdown, and the existing
hardening intent. Test first-time uv setup as well as gevent inside the actual unit: namespace/syscall/executable
memory restrictions must not silently prevent interpreter setup. If incompatibility requires a material relaxation,
surface it before changing the contract. CI retains systemd verification and security analysis; any enforced score
is measured and recorded in test/CI configuration, not README guidance.

Private temporary files remain writable; read-only assertions target the application and configuration paths from
inside the real sandbox. A plain `runuser` permission test is insufficient to prove systemd mount isolation.

### 5. Release workflow and exact-artifact verification

Use verify → source gates → prepare archive → archive gates → attest/publish. Existing reusable CI supplies the full
normal checks, while archive gates install the already-prepared bundle, check versions and dependency pins, scan the
installed runtime's licences, and exercise Linux startup. No stage rebuilds the archive after testing. Compare its
digest on transfer and bind GitHub provenance to that digest. Publish only the single archive via a draft and then
publish the draft; grant contents write only to publication and attestation permissions only where needed.

The release-existence check distinguishes a genuine missing release from authentication/network errors. Existing
releases, including partial drafts, block automatic replacement. Retain a nonpublishing manual dry run for CI
verification, not as a required maintainer step. Workflow changes still require explicit authorization before commit
or push; apply must report remote-verification blockers honestly. A new dispatch workflow may need registration on
the default branch before GitHub accepts a branch dry run.

### 6. Short documentation backed by executable tests

README release creation contains only the two annotated-tag commands after selecting `KLARO_VERSION`. Installation
contains a fixed `v0.1.0` download URL and archive filename, not installation version variables. Update these fixed
examples when releasing a newer version; the prepared archive's README must match its version. Keep a single
clearly marked example block for this replacement and test it independently of the source placeholder.

The operator sequence is: system-wide uv prerequisite, useradd, download/unpack, directory permissions, install/edit
configuration, manual launcher, then optional systemd symlink/reload/enable. Explain initial Internet access briefly.
Remove the superseded release-install environment variables and multi-asset/checksum/tool-install procedures,
release upgrade/rollback section, systemd-score advice, and offline variation. Preserve existing data backup and
fresh-directory rules and keep Caddy concise alongside Nginx.

Tests execute marked operation blocks. A local download fixture may substitute only the GitHub origin for the test
server; it must preserve the documented fixed tag/path layout rather than injecting installation variables back
into README. Verify both manual startup and systemd on the same archive, locked runtime dependencies, no-dev setup,
read-only application/configuration, restart persistence, invalid-config restart limiting, and Caddy's client IP
and status/heartbeat/answer events. Replace the broken old tampering fixture rather than mapping removed scenarios
to unrelated tests. Retain archive integrity checks within CI tests.

### 7. Anonymous-request resource impact

Runtime preparation occurs at process startup only, never in response to anonymous HTTP input. It introduces no
request-keyed caches, allocations, subprocesses, or new routes. Existing input bounds, capability URLs, single-worker
limits, browser-only answers, CSP, no-JavaScript behavior, and accessibility contracts remain covered by the full
suite. No storage schema changes are needed.

## Risks / Trade-offs

- [Initial startup downloads can fail or take time] → report startup failures, retain restart limits, and exercise
  cold startup under the actual unit rather than only a preinstalled environment.
- [Source builds write into root-owned source] → build the bundled wheel in CI; prohibit server-side dependency
  builds and verify hashed runtime requirements against the staged lock. Platforms without suitable wheels fail
  explicitly rather than resolving or building different dependencies.
- [Manual and systemd startup overlap] → document stopping the manual instance first and test clean shutdown.
- [A fixed README version can drift] → test the release-staged example against its tag; maintain the source example
  at the latest published release independently of the source placeholder.

## Migration Plan

This replaces an unfinished deployment plan; no production installation or data migration is assumed. During apply,
reconcile the earlier uncommitted files and reopen affected checks. Preserve the existing storage rule: format-changing
deployments require a fresh data directory and never automatic migration or deletion. Restoration of a previous build
remains an operator action with one stopped instance, not an added release rollback tutorial.
