"""Small setuptools hook to ship the exact uv.lock inside wheels."""

from pathlib import Path
from shutil import copy2

from setuptools import setup
from setuptools.command.build_py import build_py


class BuildPy(build_py):
    def run(self) -> None:
        super().run()
        target = Path(self.build_lib) / "klaro" / "uv.lock"
        target.parent.mkdir(parents=True, exist_ok=True)
        copy2(Path(__file__).parent / "uv.lock", target)


setup(cmdclass={"build_py": BuildPy})
