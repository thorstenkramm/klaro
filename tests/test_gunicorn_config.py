from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


def test_packaged_gunicorn_config_uses_toml_and_one_bounded_gevent_worker(
    tmp_path: Path, monkeypatch
) -> None:
    config = tmp_path / "klaro.toml"
    config.write_text(
        f"""[pushover]
app_token = "{"a" * 30}"

[klaro]
data_dir = "{tmp_path / "data"}"
public_address = "https://klaro.example.com"
listen = "127.0.0.1:3344"
"""
    )
    monkeypatch.setenv("KLARO_CONFIG", str(config))

    settings = importlib.import_module("klaro.gunicorn_conf")

    assert settings.bind == "127.0.0.1:3344"
    assert settings.workers == 1
    assert settings.worker_class == "gevent"
    assert settings.worker_connections == 1000
    assert settings.preload_app is False


def test_post_worker_init_starts_worker_scheduler_once() -> None:
    settings = importlib.import_module("klaro.gunicorn_conf")
    scheduler = Mock()
    worker = SimpleNamespace(
        wsgi=SimpleNamespace(extensions={"klaro": SimpleNamespace(scheduler=scheduler)}),
        log=Mock(),
    )

    settings.post_worker_init(worker)

    scheduler.start.assert_called_once_with()
    worker.log.info.assert_called_once_with("Klaro cleanup scheduler started")
