"""Coordinate pending persistence, Pushover acceptance, and publication."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from klaro.config import Config
from klaro.filestore import FileStore
from klaro.models import Question
from klaro.pushover import PushoverAcceptance
from klaro.records import Questionnaire


class Notifier(Protocol):
    def send(
        self,
        *,
        recipient: str,
        questioner: str,
        questions: Sequence[Question],
        url: str,
    ) -> PushoverAcceptance: ...


@dataclass(frozen=True, slots=True)
class CreationResult:
    record: Questionnaire
    url: str


class QuestionnaireCreator:
    def __init__(self, config: Config, store: FileStore, notifier: Notifier) -> None:
        self.config = config
        self.store = store
        self.notifier = notifier

    def create(
        self, *, recipient: str, questioner: str, questions: Sequence[Question]
    ) -> CreationResult:
        pending = self.store.create_pending(
            questions=questions,
            questioner=questioner,
            lifetime_seconds=self.config.klaro.lifetime_seconds,
        )
        url = self.config.klaro.questionnaire_url(pending.token)
        try:
            acceptance = self.notifier.send(
                recipient=recipient,
                questioner=questioner,
                questions=questions,
                url=url,
            )
            published = self.store.publish(pending.token, pushover_request=acceptance.request_id)
        except Exception:
            self.store.discard_pending(pending.token)
            raise
        return CreationResult(record=published, url=url)
