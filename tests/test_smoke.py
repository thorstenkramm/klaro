import tomllib
from pathlib import Path

import klaro


def test_package_import() -> None:
    with (Path(__file__).parent.parent / "pyproject.toml").open("rb") as stream:
        project = tomllib.load(stream)

    assert klaro.__version__ == project["project"]["version"]
