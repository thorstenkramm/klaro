"""Worker-owned periodic questionnaire cleanup."""

from __future__ import annotations

import logging
import threading

from klaro.filestore import FileStore

LOGGER = logging.getLogger(__name__)


class CleanupScheduler:
    def __init__(self, store: FileStore, *, interval_seconds: float = 30) -> None:
        if interval_seconds <= 0:
            raise ValueError("Cleanup interval must be positive")
        self.store = store
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._guard = threading.Lock()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        with self._guard:
            if self.running:
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="klaro-cleanup", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._guard:
            self._stop.set()
            thread = self._thread
            self._thread = None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                self.store.cleanup_expired()
            except Exception:  # Keep transient filesystem failures from killing cleanup.
                LOGGER.exception("Questionnaire cleanup failed")
