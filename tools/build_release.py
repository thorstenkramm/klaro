"""Build a versioned, single-file deployment bundle in an isolated staging tree."""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import tarfile
import tempfile
import tomllib
from pathlib import Path

from tools.release_check import Release, check_release, project_version

PROJECT_FILES = ("pyproject.toml", "uv.lock", "setup.py", "MANIFEST.in", "README.md", "LICENSE")
DEPLOY_FILES = {
    "deploy/bin/klaro": "bin/klaro",
    "deploy/klaro.example.toml": "klaro.example.toml",
    "deploy/systemd/klaro.service": "klaro.service",
    "deploy/caddy/Caddyfile": "Caddyfile",
}


def run_uv(project: Path, *arguments: str) -> str:
    # Fixed executable and argument lists; no shell or request input is evaluated.
    result = subprocess.run(  # noqa: S603
        ["uv", *arguments],  # noqa: S607 - uv is supplied by the maintainer/CI PATH.
        cwd=project,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def copy_file(source: Path, target: Path) -> None:
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"Release input must be a regular file: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    target.chmod(0o644)


def stage_project(repository: Path, target: Path, release: Release) -> None:
    for name in PROJECT_FILES:
        copy_file(repository / name, target / name)
    for source in sorted((repository / "src/klaro").rglob("*")):
        if source.is_symlink():
            raise ValueError(f"Symlink in release source: {source}")
        if source.is_file() and "__pycache__" not in source.parts and source.suffix != ".pyc":
            copy_file(source, target / source.relative_to(repository))
    old_version = project_version(target / "pyproject.toml")
    project = target / "pyproject.toml"
    text, count = re.subn(
        r'(?m)^version = "' + re.escape(old_version) + r'"$',
        f'version = "{release.version}"',
        project.read_text(),
        count=1,
    )
    if count != 1:
        raise ValueError("Cannot locate project version")
    project.write_text(text)
    lock = target / "uv.lock"
    text, count = re.subn(
        r'(?m)^(name = "klaro"\nversion = ")' + re.escape(old_version) + r'"$',
        lambda match: match[1] + release.version + '"',
        lock.read_text(),
        count=1,
    )
    if count != 1:
        raise ValueError("Cannot locate Klaro lock metadata")
    lock.write_text(text)
    before = tomllib.loads((repository / "uv.lock").read_text())["package"]
    after = tomllib.loads(lock.read_text())["package"]
    if [p for p in before if p["name"] != "klaro"] != [p for p in after if p["name"] != "klaro"]:
        raise ValueError("Release preparation changed dependency locks")


def build_bundle(repository: Path, output: Path, tag: str) -> Path:
    release = check_release(tag)
    output.mkdir(parents=True, exist_ok=True)
    archive = output / release.archive_name
    with tempfile.TemporaryDirectory(prefix="klaro-release-") as temporary:
        staging = Path(temporary) / "project"
        stage_project(repository, staging, release)
        run_uv(staging, "lock", "--check")
        wheels = Path(temporary) / "wheels"
        run_uv(staging, "build", "--wheel", "--out-dir", str(wheels))
        bundle = Path(temporary) / "bundle"
        stage_project(repository, bundle, release)
        for source, destination in DEPLOY_FILES.items():
            copy_file(repository / source, bundle / destination)
        (bundle / "bin/klaro").chmod(0o755)
        (wheel,) = wheels.glob("*.whl")
        copy_file(wheel, bundle / "wheelhouse" / wheel.name)
        requirements = run_uv(
            staging,
            "export",
            "--locked",
            "--no-dev",
            "--no-emit-project",
            "--no-header",
        )
        digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
        (bundle / "requirements.txt").write_text(
            requirements + f"\n./wheelhouse/{wheel.name} --hash=sha256:{digest}\n"
        )
        readme = bundle / "README.md"
        text = readme.read_text()
        text = re.sub(
            r"releases/download/v[^/\s]+/klaro-[^\s\"/]+\.tar\.gz",
            f"releases/download/{release.tag}/{release.archive_name}",
            text,
        )
        readme.write_text(text)
        with tarfile.open(archive, "w:gz") as result:
            for path in sorted(bundle.rglob("*")):
                result.add(path, arcname=str(path.relative_to(bundle)), recursive=False)
    return archive


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag")
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("release"))
    args = parser.parse_args()
    print(build_bundle(args.repository.resolve(), args.output.resolve(), args.tag))


if __name__ == "__main__":
    main()
