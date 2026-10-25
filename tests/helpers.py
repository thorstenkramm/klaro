from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass
class FakeClock:
    current: datetime = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
    monotonic_seconds: float = 0.0

    def wall(self) -> datetime:
        return self.current

    def monotonic(self) -> float:
        return self.monotonic_seconds

    def advance(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)
        self.monotonic_seconds += seconds
