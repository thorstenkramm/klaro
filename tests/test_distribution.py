from __future__ import annotations

import os
import socket
import subprocess
import tarfile
from pathlib import Path
from zipfile import ZipFile

import requests

from tests.process_helpers import stop_process_group, wait_until_serving


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def test_distributions_install_and_start_outside_source_tree(tmp_path: Path) -> None:
    repository = Path(__file__).parent.parent
    distribution = tmp_path / "dist"
    subprocess.run(
        ["uv", "build", "--out-dir", str(distribution)],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    wheel = next(distribution.glob("klaro-*.whl"))
    source = next(distribution.glob("klaro-*.tar.gz"))

    required_wheel = {
        "klaro/uv.lock",
        "klaro/cli.py",
        "klaro/THIRD_PARTY_NOTICES.md",
        "klaro/templates/base.html",
        "klaro/templates/questionnaire.html",
        "klaro/templates/_answer_form.html",
        "klaro/templates/_answered.html",
        "klaro/templates/_questionnaire_fragment.html",
        "klaro/static/vendor/uikit/uikit.min.css",
        "klaro/static/vendor/uikit/LICENSE.md",
        "klaro/static/vendor/htmx/htmx.min.js",
        "klaro/static/vendor/htmx/LICENSE",
        "klaro/licenses/markdown-it-py.txt",
        "klaro/licenses/mdurl.txt",
    }
    with ZipFile(wheel) as archive:
        assert required_wheel <= set(archive.namelist())
        assert archive.read("klaro/uv.lock") == (repository / "uv.lock").read_bytes()

    prefix = "klaro-0.1.0"
    required_source = {
        f"{prefix}/uv.lock",
        f"{prefix}/pyproject.toml",
        f"{prefix}/README.md",
        f"{prefix}/LICENSE",
        *{f"{prefix}/src/{name}" for name in required_wheel - {"klaro/uv.lock"}},
    }
    with tarfile.open(source, "r:gz") as archive:
        assert required_source <= set(archive.getnames())

    environment_root = tmp_path / "clean-environment"
    clean_working_directory = tmp_path / "clean-working-directory"
    clean_working_directory.mkdir()
    subprocess.run(["uv", "venv", str(environment_root)], check=True, capture_output=True)
    python = environment_root / "bin" / "python"
    launcher = environment_root / "bin" / "klaro"
    subprocess.run(
        ["uv", "pip", "install", "--python", str(python), str(wheel)],
        cwd=clean_working_directory,
        check=True,
        capture_output=True,
        text=True,
    )

    token = "w" * 43
    seed_script = """
import sys
from pathlib import Path
from importlib.resources import files
import klaro
from klaro.models import Question
from klaro.filestore import FileStore
from klaro.markdown import plain_name

assert files("klaro").joinpath("uv.lock").is_file()
assert files("klaro").joinpath("licenses/markdown-it-py.txt").is_file()
assert plain_name("Drink **now**?") == "Drink now?"
store = FileStore(Path(sys.argv[1]), token_factory=lambda: sys.argv[2])
store.create_pending(
    questions=[Question(
        id="q1",
        name="Drink **now**?",
        kind="radio",
        answers=("beer `cold`\\n```\\nx\\n```", "water"),
    )],
    questioner="Wheel test",
    lifetime_seconds=300,
)
store.publish(sys.argv[2])
print(klaro.__file__)
"""
    seeded = subprocess.run(
        [str(python), "-c", seed_script, str(tmp_path / "installed-data"), token],
        cwd=clean_working_directory,
        check=False,
        capture_output=True,
        text=True,
    )
    assert seeded.returncode == 0, seeded.stderr
    assert str(environment_root) in seeded.stdout
    assert str(repository) not in seeded.stdout

    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    config = clean_working_directory / "klaro.toml"
    config.write_text(
        f"""[pushover]
app_token = "{"a" * 30}"

[klaro]
data_dir = "{tmp_path / "installed-data"}"
public_address = "{base_url}"
listen = "127.0.0.1:{port}"
lifetime_seconds = 300
"""
    )
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("KLARO_CONFIG", None)
    log_path = tmp_path / "installed-gunicorn.log"
    process = None
    with log_path.open("w") as log_file:
        try:
            process = subprocess.Popen(
                [str(launcher), "--config", str(config)],
                cwd=clean_working_directory,
                env=environment,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            wait_until_serving(process, base_url)

            page = requests.get(f"{base_url}/{token}", headers={"Accept": "text/html"}, timeout=2)
            assert page.status_code == 200
            assert "Drink <strong>now</strong>?" in page.text
            assert "<code>cold</code>" in page.text
            assert '<pre tabindex="0" aria-label="Code block">' in page.text
            assert "/static/vendor/uikit/uikit.min.css" in page.text
            assert (
                requests.get(f"{base_url}/static/vendor/uikit/LICENSE.md", timeout=2).status_code
                == 200
            )
            assert process.poll() is None
        finally:
            stop_process_group(process)

    logs = log_path.read_text()
    assert logs.count("Klaro cleanup scheduler started") == 1
    assert token not in logs
    assert "/<redacted>" in logs
