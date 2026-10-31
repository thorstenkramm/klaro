# Spec Delta

## Purpose

Defines a short Linux installation path from one release archive to a locked, unprivileged Klaro instance supervised by systemd and optionally exposed through Caddy.

## ADDED Requirements

### Requirement: Simple archive installation

The README SHALL document system-wide uv, a persistent unprivileged `klaro` user, one archive download, extraction into root-owned `/opt/klaro`, configuration, and startup. The installation URL SHALL use the fixed first version `v0.1.0`, updated to the latest release when published, rather than installation variables. No separate `uv tool install` step SHALL be required.

#### Scenario: Install a release

- **WHEN** an operator follows the installation instructions with system-wide uv available
- **THEN** the archive is extracted directly into `/opt/klaro` with an executable `bin/klaro` launcher
- **AND** configuration is owned by `root:klaro` with mode `0640`, and state directories are owned by `klaro` with mode `0700`

### Requirement: Locked first startup

The bundled launcher SHALL use `/usr/local/bin/uv` and bundled lock metadata to prepare the runtime automatically and run with `/etc/klaro/klaro.toml`. Python downloads, environment files, and caches SHALL reside under `/var/lib/klaro`. Initial startup MAY require network access. The application directory SHALL remain unmodified by the service user.

#### Scenario: First startup without a prepared environment

- **WHEN** user `klaro` starts `/opt/klaro/bin/klaro` with Internet access and valid configuration
- **THEN** required runtime dependencies are installed at their locked versions and Klaro starts
- **AND** runtime setup writes no files into `/opt/klaro` or inaccessible home directories

#### Scenario: Restart uses prepared runtime

- **WHEN** the same release is restarted with its runtime already prepared
- **THEN** it retains the locked dependency versions and existing questionnaire records

### Requirement: Supervised single-instance service

The shipped systemd unit SHALL use the same launcher as manual startup, run as `klaro`, start at boot when enabled, restart failures with rate limiting, and run exactly one gevent worker. The README SHALL show symlinking `/opt/klaro/klaro.service`, daemon reload, enable/start, journal logs, and configuration restart commands.

#### Scenario: Service starts at boot

- **WHEN** the operator stops any manual instance and enables the linked unit
- **THEN** the service is enabled for boot and starts one Klaro instance with one gevent worker as `klaro`

#### Scenario: Invalid configuration

- **WHEN** configuration validation fails
- **THEN** the journal contains the configuration error without secrets and repeated starts are rate-limited

### Requirement: Service isolation

The unit SHALL prevent privilege escalation and application/configuration writes, hide home directories, provide private temporary files and devices, and restrict network families to IP and Unix sockets. Persistent runtime and questionnaire writes SHALL be confined to `/var/lib/klaro`. Private temporary files are permitted.

#### Scenario: Application and configuration are read-only

- **WHEN** code running inside the service sandbox attempts writes to `/opt/klaro` and `/etc/klaro`
- **THEN** those writes fail while runtime setup and questionnaire writes under `/var/lib/klaro` succeed

#### Scenario: Unit passes validation

- **WHEN** CI checks the unit's syntax, hardening, first startup, and request handling on Linux
- **THEN** validation succeeds and sandbox settings permit the required runtime behavior

### Requirement: Reverse-proxy contract

The documented proxies SHALL terminate TLS, forward to `klaro.listen`, overwrite `X-Forwarded-For` with the direct client's address, stream SSE promptly, and preserve Klaro's security headers. A Caddy example SHALL accompany Nginx and specify matching trusted-proxy settings.

#### Scenario: Client address through Caddy

- **WHEN** a client supplies forged forwarding headers through the configured trusted Caddy proxy
- **THEN** Klaro's abuse controls use the real client address

#### Scenario: Answer stream through Caddy

- **WHEN** a questioner waits on an SSE stream through Caddy
- **THEN** status, heartbeat, and answer events arrive without proxy buffering

#### Scenario: Example configuration is valid

- **WHEN** the shipped Caddyfile is validated
- **THEN** Caddy accepts it

### Requirement: Focused operator documentation

The release installation guide SHALL omit release upgrade/rollback procedures, systemd exposure-score advice, offline-install variations, and uv-tool-install instructions. Detailed release verification and hardening checks SHALL remain in CI. Existing storage-format and single-instance safeguards SHALL remain documented.

#### Scenario: Reader follows the basic guide

- **WHEN** a reader follows installation and systemd setup
- **THEN** the guide provides the download, configuration, startup, and supervision steps without the removed procedures
