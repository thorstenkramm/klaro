# Tasks

Feedback 02 supersedes the original installation/version plan. Only unchanged, previously verified work remains
checked; reopened tasks include adapting earlier partial implementations. Historical 13/17 completion is not evidence
that the revised contract is implemented.

## 1. Release version and archive

- [x] 1.1 Read `klaro.__version__` from installed metadata and compare it with project metadata in the smoke test; smoke tests and strict mypy passed in the earlier implementation.
- [x] 1.2 Set the source version to `0.0.0.dev0` and synchronize source lock metadata; revise the release checker to derive versions from tags, with tests for stable, prerelease, malformed, and missing-prefix tags and canonical filenames. Verify version reporting in an installed release and unchanged source metadata.
- [x] 1.3 Add a staged archive builder with the explicit layout in design.md, version injection, unchanged third-party lock entries, executable launcher mode, and complete assets/licences/build inputs. Test safe member paths, exclusion of local files, lock consistency, and extraction without a wrapper directory.
- [x] 1.4 Replace multi-asset release documentation with the two tag commands and fixed first-release download URL; verify staged README examples match each generated version and no manual source-version bump is required.

## 2. Locked launcher and systemd

- [ ] 2.1 Add the shared launcher with absolute uv/config paths, hashed runtime-only requirements and bundled-wheel installation, state-local environment/cache/Python, and exec-based startup. Verify cold setup, hash rejection, no server-side builds, signal shutdown, and zero writes to read-only release sources.
- [ ] 2.2 Add `klaro.example.toml`, revise the systemd ExecStart for the shared launcher, and replace the sysusers path with documented useradd. Adapt packaging/file tests and validate configuration defaults, owner/group/modes, symlink installation, restart limits, and required hardening.
- [x] 2.3 Ship the Caddy example with explicit forwarding-header replacement and immediate SSE flushing; its file tests and local `caddy validate` passed in the earlier implementation.
- [x] 2.4 Embed the shipped Caddyfile exactly in README alongside Nginx with matching trusted proxies; the existing documentation consistency test passed.
- [ ] 2.5 Rewrite executable README blocks for one download, extraction, restricted configuration, manual launcher, and optional systemd setup. Remove superseded uv-tool, upgrade/rollback, score, and offline instructions while preserving data-format safeguards; verify shell syntax, fixed URLs, and absence of removed procedures.

## 3. Archive and Linux integration tests

- [ ] 3.1 Adapt distribution tests to check the deployment bundle separately from ordinary wheel/sdist output, retaining installed metadata/assets tests; verify built archives contain all runtime/build inputs and no obsolete sysusers asset.
- [ ] 3.2 Rework opt-in Linux tests to execute the README sequence against the prepared archive with only a download-origin substitution. Verify manual and systemd cold startup, locked runtime-only packages, application/config permissions, actual sandbox write denial, one worker, restart persistence, and invalid-config journal/start limiting. Confirm ordinary local tests skip privileged execution.
- [ ] 3.3 Exercise Caddy forwarding and status/heartbeat/answer streams against the archive-installed service; validate Caddy and systemd, measure hardening in CI configuration, and verify first-time uv setup succeeds under the actual sandbox. Remove superseded upgrade and installation-checksum scenarios.

## 4. Release workflow

- [x] 4.1 Make CI reusable with mutation disabled by default while preserving existing triggers; actionlint and zizmor passed for that earlier change.
- [ ] 4.2 Revise the workflow to prepare one archive, run source and exact-archive gates, transfer/compare its digest, attest it, and publish only that tested archive without rebuilding. Test graph dependencies, least-privilege permissions, existing-release/error handling, prerelease classification, draft publication, and a nonpublishing dry-run guard; run workflow linters without silently adding exceptions.
- [ ] 4.3 Wire the Ubuntu deployment job to consume the prepared archive rather than independently rebuilding it, and validate installed runtime licences and archive integrity. Verify the real Linux job and release dry run when remote execution is available; obtain explicit authorization before any commit/push and leave this task unchecked if blocked.

## 5. Integration and review

- [x] 5.1 Replace the scenario matrix's superseded version-match, multi-asset, checksum-installation, and upgrade scenarios with every revised release/deployment scenario; retain this change in IMPLEMENTED_DELTAS and verify matrix/simulated-sync tests pass.
- [ ] 5.2 Prove new regression tests fail under representative broken version injection, missing archive content, writable application paths, and removed publish guards; restore the implementation and verify those tests pass.
- [ ] 5.3 Run all AGENTS.md and CI gates, including coverage/browser/axe checks, strict OpenSpec validation, duplication, workflow linting, and security/licence scans. Use the reviewer subagent and resolve findings; record local versus remote verification accurately.

## Workflow follow-up

- With explicit authorization, merge and publish the first `v0.1.0` release; verify the published archive and provenance.
- Update the source README's fixed installation version with each subsequent published release.
- Archive the completed change and remove it from IMPLEMENTED_DELTAS after spec synchronization.
