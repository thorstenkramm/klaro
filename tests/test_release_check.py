from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tools.release_check import ReleaseCheckError, check_release, project_version


@pytest.mark.parametrize(
    ("tag", "version", "prerelease"),
    [("v0.1.0", "0.1.0", False), ("v1.3.0rc1", "1.3.0rc1", True), ("v1.2.0RC1", "1.2.0rc1", True)],
)
def test_tag_derives_canonical_release(tag: str, version: str, prerelease: bool) -> None:
    release = check_release(tag)
    assert release.tag == tag
    assert release.version == version
    assert release.is_prerelease is prerelease
    assert release.archive_name == f"klaro-{version}.tar.gz"


@pytest.mark.parametrize("tag", ["1.2.0", "v", "vnot-a-version", "v1.0\n"])
def test_invalid_release_tags_are_rejected(tag: str) -> None:
    with pytest.raises(ReleaseCheckError):
        check_release(tag)


def test_cli_reports_release_candidate() -> None:
    command = subprocess.run(
        [sys.executable, "tools/release_check.py", "v1.3.0rc1"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert command.stdout.splitlines() == [
        "version=1.3.0rc1",
        "prerelease=true",
        "tag=v1.3.0rc1",
        "archive=klaro-1.3.0rc1.tar.gz",
    ]


def test_source_placeholder_and_documented_tag() -> None:
    repository = Path(__file__).parent.parent
    assert project_version(repository / "pyproject.toml") == "0.0.0.dev0"
    assert check_release("v0.1.0").version == "0.1.0"
    assert 'git tag -a "v$KLARO_VERSION"' in (repository / "README.md").read_text()


def test_cli_failure_does_not_print_release_outputs() -> None:
    command = subprocess.run(
        [sys.executable, "tools/release_check.py", "invalid"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert command.returncode == 1
    assert command.stdout == ""
    assert "must start with 'v'" in command.stderr
