"""Gunicorn production settings loaded with -c python:klaro.gunicorn_conf."""

from __future__ import annotations

from typing import Any

from klaro.config import load_config

_config = load_config()

bind = _config.klaro.listen
workers = 1
worker_class = "gevent"
worker_connections = 1000
preload_app = False
accesslog = "-"
errorlog = "-"
loglevel = "info"


def post_worker_init(worker: Any) -> None:
    """Start cleanup only in the initialized worker, never in the master."""
    worker.wsgi.extensions["klaro"].scheduler.start()
    worker.log.info("Klaro cleanup scheduler started")
