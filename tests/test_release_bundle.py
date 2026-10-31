from __future__ import annotations

import os
import subprocess
import tarfile
import tomllib
from pathlib import Path

import pytest

from tools.build_release import build_bundle, stage_project
from tools.release_check import check_release

ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    directory = tmp_path_factory.mktemp("bundle")
    original = {name: (ROOT / name).read_bytes() for name in ("pyproject.toml", "uv.lock")}
    archive = build_bundle(ROOT, directory, "v0.1.0")
    unpacked = directory / "unpacked"
    with tarfile.open(archive) as source:
        for member in source.getmembers():
            assert not member.name.startswith("/")
            assert ".." not in Path(member.name).parts
            assert member.isfile() or member.isdir()
        source.extractall(unpacked, filter="data")
    assert original == {name: (ROOT / name).read_bytes() for name in original}
    return unpacked


def test_bundle_layout_and_version_injection(bundle: Path) -> None:
    for name in (
        "bin/klaro",
        "requirements.txt",
        "klaro.service",
        "klaro.example.toml",
        "Caddyfile",
        "LICENSE",
        "src/klaro/static/klaro/klaro.js",
    ):
        assert (bundle / name).is_file()
    assert (bundle / "bin/klaro").stat().st_mode & 0o111
    assert not (bundle / "klaro.sysusers").exists()
    assert not any(path.name in {".git", "tmp", "__pycache__"} for path in bundle.rglob("*"))
    assert tomllib.loads((bundle / "pyproject.toml").read_text())["project"]["version"] == "0.1.0"
    before = tomllib.loads((ROOT / "uv.lock").read_text())["package"]
    after = tomllib.loads((bundle / "uv.lock").read_text())["package"]
    assert [p for p in before if p["name"] != "klaro"] == [p for p in after if p["name"] != "klaro"]
    assert next(p for p in after if p["name"] == "klaro")["version"] == "0.1.0"


def test_bundle_installs_without_source_writes(bundle: Path, tmp_path: Path) -> None:
    environment = os.environ | {"UV_CACHE_DIR": str(tmp_path / "cache")}
    python = tmp_path / "venv/bin/python"
    subprocess.run(["uv", "venv", str(python.parent.parent)], check=True, env=environment)
    paths = [*bundle.rglob("*"), bundle]
    modes = {path: path.stat().st_mode & 0o777 for path in paths}
    try:
        for path in paths:
            path.chmod(0o555 if path.is_dir() else 0o444)
        subprocess.run(
            [
                "uv",
                "pip",
                "sync",
                "--require-hashes",
                "--only-binary",
                ":all:",
                "--python",
                str(python),
                "requirements.txt",
            ],
            cwd=bundle,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        result = subprocess.run(
            [str(python), "-c", "import klaro; print(klaro.__version__)"],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            text=True,
        )
        assert result.stdout.strip() == "0.1.0"
        packages = subprocess.run(
            ["uv", "pip", "list", "--python", str(python)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        assert "pytest" not in packages
        assert "ruff" not in packages
    finally:
        for path, mode in modes.items():
            path.chmod(mode)


def test_stage_injects_prerelease_version(tmp_path: Path) -> None:
    stage_project(ROOT, tmp_path / "staged", check_release("v1.2.0rc1"))
    assert (
        tomllib.loads((tmp_path / "staged/pyproject.toml").read_text())["project"]["version"]
        == "1.2.0rc1"
    )


def test_archive_readme_matches_release_version(tmp_path: Path) -> None:
    archive = build_bundle(ROOT, tmp_path, "v1.2.0rc1")
    with tarfile.open(archive) as source:
        stream = source.extractfile("README.md")
        assert stream is not None
        readme = stream.read().decode()
    assert "releases/download/v1.2.0rc1/klaro-1.2.0rc1.tar.gz" in readme
    assert "releases/download/v0.1.0/" not in readme
