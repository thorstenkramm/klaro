"""Worker-local questionnaire subscriptions with race-free state rechecks."""

from __future__ import annotations

import threading
from dataclasses import dataclass

from klaro.storage import FileStore, Questionnaire, QuestionnaireNotFound


@dataclass
class _HubEntry:
    condition: threading.Condition
    version: int = 0
    subscribers: int = 0


class Subscription:
    def __init__(
        self,
        hub: SubscriberHub,
        token: str,
        entry: _HubEntry,
        initial: Questionnaire,
    ) -> None:
        self.hub = hub
        self.store = hub.store
        self.token = token
        self.entry = entry
        self.initial = initial
        self.expires_at = initial.expires_at
        self._version = entry.version
        self._closed = False

    def snapshot(self) -> tuple[str, Questionnaire | None]:
        """Return status, answer, or expired using current persistent state."""
        try:
            record = self.store.get_public(self.token)
        except QuestionnaireNotFound:
            if self.store.clock.wall() >= self.expires_at:
                return "expired", None
            raise
        if record.status == "answered":
            return "answer", record
        return "status", record

    def wait_for_change(self, timeout: float) -> tuple[str, Questionnaire | None]:
        """Wait for a transition, returning heartbeat on a timeout or spurious wakeup."""
        with self.entry.condition:
            if self._version == self.entry.version:
                self.entry.condition.wait(timeout)
            self._version = self.entry.version
        event, record = self.snapshot()
        if event == "status":
            return "heartbeat", record
        return event, record

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.hub._unsubscribe(self.token, self.entry)

    def __enter__(self) -> Subscription:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class SubscriberHub:
    def __init__(self, store: FileStore) -> None:
        self.store = store
        self._entries: dict[str, _HubEntry] = {}
        self._guard = threading.Lock()
        store.add_transition_listener(self.notify)

    def _entry(self, token: str) -> _HubEntry:
        with self._guard:
            return self._entries.setdefault(token, _HubEntry(threading.Condition()))

    def register(self, token: str) -> Subscription:
        """Register and recheck while holding the same locks used by transitions."""
        entry = self._entry(token)
        with self.store.locked(token):
            with entry.condition:
                entry.subscribers += 1
                try:
                    initial = self.store.get_public(token)
                except Exception:
                    entry.subscribers -= 1
                    raise
                return Subscription(self, token, entry, initial)

    def notify(self, token: str, _event: str) -> None:
        entry = self._entry(token)
        with entry.condition:
            entry.version += 1
            entry.condition.notify_all()

    def _unsubscribe(self, token: str, entry: _HubEntry) -> None:
        # Entries remain allocated so a concurrent register/close cannot lose a version.
        with entry.condition:
            entry.subscribers = max(0, entry.subscribers - 1)
