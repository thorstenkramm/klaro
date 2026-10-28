"""Server-sent event framing and state-driven streaming."""

from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

from flask import Response

from klaro.clock import Clock
from klaro.records import Questionnaire, Status, format_time
from klaro.subscribers import Subscription

RETRY_FRAME = "retry: 5000\n\n"


def event_frame(event: str, data: dict[str, Any]) -> str:
    encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    lines = encoded.splitlines() or [""]
    return f"event: {event}\n" + "".join(f"data: {line}\n" for line in lines) + "\n"


def status_frame(record: Questionnaire, url: str) -> str:
    return event_frame(
        "status", {"answered_at": None, "expires_at": format_time(record.expires_at), "url": url}
    )


def answer_frame(record: Questionnaire) -> str:
    return event_frame("answer", record.answer_only_dict())


class SSEStream:
    """An iterator whose close always releases the locked registration."""

    def __init__(
        self, subscription: Subscription, *, heartbeat_seconds: float, clock: Clock, url: str
    ) -> None:
        self.subscription = subscription
        self.heartbeat_seconds = heartbeat_seconds
        self.clock = clock
        self.url = url
        self._frames = self._generate()
        self._closed = False

    def _generate(self) -> Generator[str, None, None]:
        yield RETRY_FRAME
        if self.subscription.initial.status is Status.ANSWERED:
            yield answer_frame(self.subscription.initial)
            return
        yield status_frame(self.subscription.initial, self.url)
        while True:
            event, record = self.subscription.wait_for_change(self.heartbeat_seconds)
            if event == "answer":
                if record is None:
                    raise RuntimeError("Answer event did not include a questionnaire")
                yield answer_frame(record)
                return
            if event == "expired":
                yield event_frame(
                    "expired", {"expires_at": format_time(self.subscription.expires_at)}
                )
                return
            yield event_frame("heartbeat", {"time": format_time(self.clock.wall())})

    def __iter__(self) -> SSEStream:
        return self

    def __next__(self) -> str:
        if self._closed:
            raise StopIteration
        try:
            return next(self._frames)
        except StopIteration:
            self.close()
            raise

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._frames.close()
        self.subscription.close()


def sse_response(
    subscription: Subscription, *, heartbeat_seconds: float, clock: Clock, url: str
) -> Response:
    return Response(
        SSEStream(subscription, heartbeat_seconds=heartbeat_seconds, clock=clock, url=url),
        content_type="text/event-stream; charset=utf-8",
        headers={"X-Accel-Buffering": "no"},
    )
