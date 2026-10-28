"""Per-application service container shared by request handlers."""

from __future__ import annotations

from dataclasses import dataclass

from flask import current_app

from klaro.abuse import CreationAbuseControls
from klaro.client_ip import ClientIPResolver
from klaro.clock import Clock
from klaro.config import Config
from klaro.creation import QuestionnaireCreator
from klaro.filestore import FileStore
from klaro.scheduler import CleanupScheduler
from klaro.subscribers import SubscriberHub

EXTENSION_KEY = "klaro"


@dataclass(slots=True)
class Runtime:
    config: Config
    clock: Clock
    store: FileStore
    subscribers: SubscriberHub
    creator: QuestionnaireCreator
    abuse: CreationAbuseControls
    client_ips: ClientIPResolver
    scheduler: CleanupScheduler


def get_runtime() -> Runtime:
    """Return the services of the application handling the current request."""
    runtime: Runtime = current_app.extensions[EXTENSION_KEY]
    return runtime
