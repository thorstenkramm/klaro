"""Non-retrying Pushover notification adapter."""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import requests

from klaro.config import PushoverConfig
from klaro.markdown import plain_name
from klaro.models import Question

PUSHOVER_MESSAGES_URL = "https://api.pushover.net/1/messages.json"
CONNECT_TIMEOUT_SECONDS = 3.05
READ_TIMEOUT_SECONDS = 15.0


class PushoverError(RuntimeError):
    """A notification was not accepted and queued."""

    code = "pushover_unavailable"
    http_status = 502


class PushoverRecipientRejected(PushoverError):
    """Pushover returned its structured recipient-specific error."""

    code = "recipient_rejected"
    http_status = 422


@dataclass(frozen=True, slots=True)
class PushoverAcceptance:
    request_id: str | None


class PushoverClient:
    def __init__(
        self,
        config: PushoverConfig,
        *,
        transport: Callable[..., Any] | None = None,
        timeout: tuple[float, float] = (CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
    ) -> None:
        self.config = config
        self._transport = transport or requests.post
        self._timeout = timeout
        self._outbound = threading.BoundedSemaphore(2)

    @staticmethod
    def _truncate(value: str, maximum: int) -> str:
        return value[:maximum]

    def notification_fields(
        self, *, questioner: str, questions: Sequence[Question], url: str
    ) -> dict[str, str | int]:
        if not questions:
            raise ValueError("A Pushover notification requires at least one question")
        if len(url) > 512:
            raise ValueError("The complete supplementary URL exceeds 512 characters")

        displayed_questioner = self._truncate(questioner, 100)
        title = self._truncate(f"Questionnaire from {displayed_questioner}", 250)
        url_title = self._truncate(f"Answer questionnaire from {displayed_questioner}", 100)
        prefix = f"Questioner: {displayed_questioner}\nFirst question: "
        suffix = f"\nTotal questions: {len(questions)}"
        first_question = self._truncate(
            plain_name(questions[0].name), 1024 - len(prefix) - len(suffix)
        )
        message = f"{prefix}{first_question}{suffix}"
        return {
            "title": title,
            "message": message,
            "url": url,
            "url_title": url_title,
            "sound": self.config.sound,
            "priority": self.config.priority,
        }

    def send(
        self,
        *,
        recipient: str,
        questioner: str,
        questions: Sequence[Question],
        url: str,
    ) -> PushoverAcceptance:
        """Send once and return only after Pushover explicitly accepts the notification."""
        fields = self.notification_fields(questioner=questioner, questions=questions, url=url)
        data: dict[str, str | int] = {
            "token": self.config.app_token,
            "user": recipient,
            **fields,
        }
        try:
            with self._outbound:
                response = self._transport(
                    PUSHOVER_MESSAGES_URL,
                    data=data,
                    timeout=self._timeout,
                    verify=True,
                )
        except requests.RequestException as exc:
            raise PushoverError("Pushover request failed") from exc

        try:
            payload = response.json()
        except (ValueError, TypeError):
            payload = None

        if (
            400 <= response.status_code < 500
            and response.status_code != 429
            and isinstance(payload, dict)
            and isinstance(payload.get("user"), str)
            and payload.get("status") != 1
        ):
            raise PushoverRecipientRejected("Pushover rejected the recipient key")
        if response.status_code != 200:
            raise PushoverError("Pushover did not accept the notification")
        if not isinstance(payload, dict):
            raise PushoverError("Pushover returned a malformed response")
        status = payload.get("status")
        if status != 1 or isinstance(status, bool):
            raise PushoverError("Pushover did not accept the notification")
        request_id = payload.get("request")
        return PushoverAcceptance(request_id=request_id if isinstance(request_id, str) else None)
