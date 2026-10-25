from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from klaro.cli import main


def write_config(path: Path) -> None:
    path.write_text(
        f"""[pushover]
app_token = "{"a" * 30}"

[klaro]
data_dir = "{path.parent / "data"}"
public_address = "http://127.0.0.1:3344"
"""
    )


def test_config_option_validates_and_executes_packaged_gunicorn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "my-klaro.conf"
    write_config(config)
    execute = Mock()
    monkeypatch.setattr(os, "execv", execute)
    monkeypatch.setenv("KLARO_CONFIG", "an-old-value")
    monkeypatch.chdir(tmp_path)

    main(["--config", "my-klaro.conf"])

    assert os.environ["KLARO_CONFIG"] == str(config)
    execute.assert_called_once_with(
        sys.executable,
        [
            sys.executable,
            "-m",
            "gunicorn",
            "--config",
            "python:klaro.gunicorn_conf",
            "klaro.app:create_app()",
        ],
    )


def test_short_config_option(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "klaro.toml"
    write_config(config)
    execute = Mock()
    monkeypatch.setattr(os, "execv", execute)

    main(["-c", str(config)])

    execute.assert_called_once()
    assert os.environ["KLARO_CONFIG"] == str(config)


def test_invalid_configuration_fails_before_gunicorn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "invalid.conf"
    config.write_text("")
    execute = Mock()
    monkeypatch.setattr(os, "execv", execute)

    with pytest.raises(SystemExit) as raised:
        main(["--config", str(config)])

    assert raised.value.code == 2
    assert "[pushover] must be a TOML table" in capsys.readouterr().err
    execute.assert_not_called()


def test_config_option_is_required(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        main([])

    assert raised.value.code == 2
    assert "the following arguments are required: -c/--config" in capsys.readouterr().err


def test_gunicorn_exec_failure_is_a_concise_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "klaro.toml"
    write_config(config)
    monkeypatch.setattr(os, "execv", Mock(side_effect=OSError("executable unavailable")))

    with pytest.raises(SystemExit) as raised:
        main(["--config", str(config)])

    assert raised.value.code == 1
    assert "klaro: could not start Gunicorn: executable unavailable" in capsys.readouterr().err
