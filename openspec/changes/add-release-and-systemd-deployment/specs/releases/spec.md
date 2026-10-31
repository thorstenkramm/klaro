# Spec Delta

## Purpose

Publishes tagged Klaro versions as verifiable, immutable deployment archives that operators can install with a single download.

## ADDED Requirements

### Requirement: Tag-derived release version

The source project SHALL use `0.0.0.dev0` as its version placeholder. A release SHALL derive its version from a valid `v<version>` tag and inject it into packaged project and lock metadata without a manual source-version bump. Installed `klaro.__version__` SHALL report the packaged version.

#### Scenario: Tag determines installed version

- **WHEN** tag `v0.1.0` is released from source using the placeholder
- **THEN** the archive's project metadata, lock metadata, and installed version report `0.1.0`
- **AND** the source checkout remains at the placeholder version

#### Scenario: Invalid release tag

- **WHEN** a requested release tag lacks the `v` prefix or its suffix is not a valid PEP 440 version
- **THEN** release preparation fails before an archive or GitHub Release is published

### Requirement: Single deployment archive

Each release SHALL publish one deployment asset named `klaro-<version>.tar.gz`, containing the application project, locked dependency information, launcher, example configuration, systemd unit, Caddy example, and required licences/assets. Extraction SHALL place these files directly in the target directory without another top-level directory. GitHub's automatic source downloads are not deployment assets.

#### Scenario: Complete archive layout

- **WHEN** `klaro-0.1.0.tar.gz` is extracted into `/opt/klaro`
- **THEN** `/opt/klaro/bin/klaro`, `klaro.example.toml`, `klaro.service`, and `Caddyfile` exist alongside the project and lockfile
- **AND** no separate wheel, constraints, or deployment-file download is needed

### Requirement: Release dependency consistency

Release preparation SHALL preserve the tagged source lockfile's third-party dependency versions and integrity metadata. Runtime installation SHALL select only the dependencies needed to run Klaro from that lockfile.

#### Scenario: Version injection preserves dependency pins

- **WHEN** the source placeholder is replaced with a release version
- **THEN** third-party lock entries retain their versions and hashes
- **AND** initial runtime setup does not install development dependencies

### Requirement: Releases pass every quality gate

Publication SHALL require the complete normal CI gate set for the tagged commit and successful installation and startup tests of the exact prepared deployment archive. These gates SHALL include supported Python versions, lint, typing, duplication, specifications, vulnerability, secret, licence, and Linux deployment checks.

#### Scenario: Failing gate blocks publication

- **WHEN** a required source or prepared-archive gate fails
- **THEN** no GitHub Release is published

### Requirement: Archive integrity and provenance

The deployment archive SHALL have GitHub build-provenance attestation. CI SHALL verify archive integrity across artifact transfer and publish the exact tested archive without rebuilding it. Operators SHALL NOT need separate checksum or attestation downloads for the basic installation procedure.

#### Scenario: Exact archive is published

- **WHEN** archive tests and provenance generation succeed
- **THEN** the publication input has the same digest as the tested archive
- **AND** its attestation identifies this repository's release workflow

### Requirement: Immutable and correctly classified releases

The workflow SHALL refuse to replace an existing release or its assets. PEP 440 pre-releases SHALL be marked as GitHub pre-releases and not latest; stable releases SHALL be marked latest. Failure to determine whether a release exists SHALL block publication.

#### Scenario: Re-running a published tag

- **WHEN** a release already exists for a requested tag
- **THEN** the workflow fails without changing that release or its assets

#### Scenario: Release candidate

- **WHEN** tag `v1.3.0rc1` is released
- **THEN** the GitHub Release is marked as a pre-release and not latest

### Requirement: Minimal release instructions

The documented release trigger SHALL consist of creating and pushing an annotated `v<version>` tag using `KLARO_VERSION`, with no manual project-version bump or mandatory dry run. CI MAY support an optional nonpublishing dry run.

#### Scenario: Maintainer triggers release

- **WHEN** the maintainer sets the desired version and follows the two documented Git commands
- **THEN** the pushed tag triggers release preparation with that version
