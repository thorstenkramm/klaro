# Proposal

## Why

Operators need a short, reliable path from a GitHub release to a running Klaro service. Feedback 02 replaces the
original multi-asset installation and manual version bump with one archive and a tag-driven release.

## What Changes

- Publish a single `klaro-<version>.tar.gz` deployment archive on GitHub Releases after CI succeeds. It contains
  the application project, locked dependencies, executable launcher, example TOML, systemd unit, and Caddy example.
- Keep `0.0.0.dev0` in source metadata; inject the tag version into release metadata and synchronize the bundled
  lockfile without changing dependency versions. Installed version reporting continues to use package metadata.
- Run the unpacked application through a bundled launcher using system-wide uv and locked runtime dependencies.
  The archive includes a prebuilt application wheel. First startup can download Python and dependencies;
  no server-side package build or separate `uv tool install` command is required.
- Keep `/opt/klaro` root-owned, configuration at `/etc/klaro/klaro.toml`, and writable runtime files under
  `/var/lib/klaro`. Manual startup and systemd use the same launcher and exactly one gevent worker.
- Shorten README instructions to download, unpack, configure, run, and enable systemd. Installation uses a fixed
  `v0.1.0` URL, updated with releases. Release triggering uses only the two tag/create-and-push commands.
- Retain Caddy and Nginx proxy guidance and detailed verification in CI. Remove the new release upgrade/rollback,
  systemd-score, offline-install, and uv-tool-install instructions from the operator guide.

## Capabilities

### New Capabilities

- `releases`: tag-derived versions, one deployment archive, quality gates, provenance, and immutable publication.
- `linux-deployment`: archive installation, locked first startup, supervised execution, isolation, and reverse proxies.

### Modified Capabilities

None. Application HTTP behavior and the storage-format contract remain unchanged.

## Impact

Revise `.github/workflows/release.yml`, reusable CI, `tools/release_check.py`, packaging and lock metadata,
`deploy/`, README operation blocks, distribution/deployment/workflow tests, and scenario coverage. Add a bundled
launcher and example configuration; retire the earlier sysusers-based installation path in favor of `useradd`.
No new application runtime dependency is required. Servers require system-wide uv and Internet access on initial
startup; this is one release download, not an offline bundle. This revision supersedes the original plan within
the same active change; partially implemented code must be reconciled during apply.
