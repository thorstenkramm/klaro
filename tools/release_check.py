"""Derive canonical release metadata from a version tag."""

from __future__ import annotations

import argparse
import sys
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from packaging.version import InvalidVersion, Version


class ReleaseCheckError(ValueError):
    """The requested tag cannot identify a release of this project."""


@dataclass(frozen=True, slots=True)
class Release:
    tag: str
    version: str
    is_prerelease: bool

    @property
    def archive_name(self) -> str:
        return f"klaro-{self.version}.tar.gz"


def project_version(pyproject: Path) -> str:
    with pyproject.open("rb") as stream:
        document = tomllib.load(stream)
    project = document.get("project")
    raw_version = project.get("version") if isinstance(project, dict) else None
    if not isinstance(raw_version, str):
        raise ReleaseCheckError(f"{pyproject} does not contain a string project.version")
    version = raw_version
    try:
        Version(version)
    except InvalidVersion as error:
        raise ReleaseCheckError(f"Project version {version!r} is not valid PEP 440") from error
    return version


def check_release(tag: str) -> Release:
    if not tag.startswith("v"):
        raise ReleaseCheckError(f"Release tag {tag!r} must start with 'v'")
    tagged_version = tag.removeprefix("v")
    try:
        parsed = Version(tagged_version)
    except InvalidVersion as error:
        raise ReleaseCheckError(f"Tag version {tagged_version!r} is not valid PEP 440") from error
    if any(character.isspace() for character in tag):
        raise ReleaseCheckError("Release tags must not contain whitespace")
    return Release(tag=tag, version=str(parsed), is_prerelease=parsed.is_prerelease)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", help="release tag, including its v prefix")
    arguments = parser.parse_args(argv)
    try:
        release = check_release(arguments.tag)
    except (OSError, ReleaseCheckError, tomllib.TOMLDecodeError) as error:
        print(f"release check failed: {error}", file=sys.stderr)
        return 1
    print(f"version={release.version}")
    print(f"prerelease={str(release.is_prerelease).lower()}")
    print(f"tag={release.tag}")
    print(f"archive={release.archive_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
