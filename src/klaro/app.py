"""Flask application factory."""

from __future__ import annotations

import logging
from collections.abc import Callable

from flask import Flask

from klaro import limits
from klaro.abuse import CreationAbuseControls
from klaro.assets import asset_url
from klaro.client_ip import ClientIPResolver
from klaro.clock import Clock, SystemClock
from klaro.config import Config, load_config
from klaro.creation import Notifier, QuestionnaireCreator
from klaro.filestore import FileStore
from klaro.limits import MAX_ANSWER_BODY_BYTES, MAX_BODY_BYTES
from klaro.logging_utils import install_redacting_filter
from klaro.markdown import render_name, render_option
from klaro.pushover import PushoverClient
from klaro.records import generate_token
from klaro.responses import error_response
from klaro.routes import bp
from klaro.runtime import EXTENSION_KEY, Runtime
from klaro.scheduler import CleanupScheduler
from klaro.subscribers import SubscriberHub

__all__ = ["MAX_ANSWER_BODY_BYTES", "create_app", "error_response"]

_REDACTED_LOGGERS = ("gunicorn.access", "gunicorn.error", "werkzeug")


def create_app(
    config: Config | None = None,
    *,
    clock: Clock | None = None,
    notifier: Notifier | None = None,
    token_factory: Callable[[], str] = generate_token,
    start_scheduler: bool = False,
) -> Flask:
    selected = config or load_config()
    runtime_clock = clock or SystemClock()
    store = FileStore(
        selected.klaro.data_dir,
        token_factory=token_factory,
        clock=runtime_clock,
        unreadable_retention_seconds=selected.klaro.lifetime_seconds,
    )
    runtime = Runtime(
        config=selected,
        clock=runtime_clock,
        store=store,
        subscribers=SubscriberHub(store),
        creator=QuestionnaireCreator(
            selected, store, notifier or PushoverClient(selected.pushover)
        ),
        abuse=CreationAbuseControls(runtime_clock),
        client_ips=ClientIPResolver(selected.klaro.trusted_proxies),
        scheduler=CleanupScheduler(store),
    )

    app = Flask(__name__)
    app.jinja_env.globals.update(
        render_name=render_name, render_option=render_option, limits=limits, asset_url=asset_url
    )
    app.config["MAX_CONTENT_LENGTH"] = MAX_BODY_BYTES
    app.extensions[EXTENSION_KEY] = runtime
    for logger in (app.logger, *map(logging.getLogger, _REDACTED_LOGGERS)):
        install_redacting_filter(logger)
    app.register_blueprint(bp)

    if start_scheduler:
        runtime.scheduler.start()
    return app
