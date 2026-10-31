from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent


def workflow():
    return yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text())


def test_all_gates_block_publication_and_dry_run_never_publishes() -> None:
    jobs = workflow()["jobs"]
    assert jobs["gates"]["needs"] == "verify"
    assert jobs["prepare"]["needs"] == ["verify", "gates"]
    assert jobs["archive-gates"]["needs"] == ["verify", "prepare"]
    assert jobs["attest"]["needs"] == ["prepare", "archive-gates"]
    assert jobs["publish"]["needs"] == ["verify", "prepare", "attest"]
    assert jobs["publish"]["if"] == (
        "github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')"
    )
    assert jobs["attest"]["permissions"] == {
        "contents": "read",
        "id-token": "write",
        "attestations": "write",
    }
    assert jobs["publish"]["permissions"] == {"contents": "write"}


def test_publish_uses_only_tested_archive_and_provenance() -> None:
    jobs = workflow()["jobs"]
    for name in ("attest", "publish"):
        steps = jobs[name]["steps"]
        assert steps[0]["uses"].startswith("actions/download-artifact@")
        assert steps[0]["with"] == {"name": "release", "path": "release"}
        script = "\n".join(step.get("run", "") for step in steps)
        assert "sha256sum --check" in script
        assert "uv build" not in script
        assert "build_release" not in script
        assert not any("checkout@" in step.get("uses", "") for step in steps)
    assert jobs["attest"]["steps"][-1]["with"]["subject-paths"] == "release/*.tar.gz"
    publish = jobs["publish"]["steps"][-1]["run"]
    assert 'gh release create "$RELEASE_TAG" "${archive[0]}"' in publish
    assert "--draft=false" in publish
    assert "--prerelease --latest=false" in publish


def test_existing_release_and_api_errors_block_release() -> None:
    jobs = workflow()["jobs"]
    for name in ("verify", "publish"):
        script = jobs[name]["steps"][-1]["run"]
        # No negation/|| fallback on the API request: shell failure is fatal, not 'absent'.
        api = next(line.strip() for line in script.splitlines() if "gh api" in line)
        assert api.startswith("gh api --paginate ")
        assert "||" not in api
        assert "grep -Fxq" in script
        assert "exit 1" in script


def test_deployment_consumes_prepared_artifact() -> None:
    jobs = workflow()["jobs"]
    assert jobs["archive-gates"]["uses"] == "./.github/workflows/deployment.yml"
    assert jobs["archive-gates"]["with"] == {
        "artifact": "release",
        "digest": "${{ needs.prepare.outputs.digest }}",
        "version": "${{ needs.verify.outputs.version }}",
    }
    document = yaml.safe_load((ROOT / ".github/workflows/deployment.yml").read_text())
    steps = document["jobs"]["deployment"]["steps"]
    scripts = "\n".join(step.get("run", "") for step in steps)
    assert "build_release" not in scripts
    assert "KLARO_RELEASE_ARCHIVE=" in scripts
    assert "sha256sum --check" in scripts


def test_ci_is_reusable_with_mutation_disabled_by_default() -> None:
    document = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    triggers = document.get("on", document.get(True))
    assert triggers["workflow_call"]["inputs"]["mutation"]["default"] is False
    assert triggers["push"] == {"branches": ["main"]}
