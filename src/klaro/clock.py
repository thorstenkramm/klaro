"""Injectable wall and monotonic clocks."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def wall(self) -> datetime:
        """Return the current timezone-aware wall time."""

    def monotonic(self) -> float:
        """Return monotonic seconds for in-memory intervals."""


class SystemClock:
    def wall(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        return time.monotonic()
