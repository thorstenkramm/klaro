from __future__ import annotations

import re
from pathlib import Path

from klaro.abuse import CreationRateLimiter, RecipientBackoff
from tests.helpers import FakeClock

README = (Path(__file__).parent.parent / "README.md").read_text()
IP = "192.0.2.10"


def test_documented_fixed_window_values_and_retry_example(fake_clock: FakeClock) -> None:
    match = re.search(
        r"\*\*(\d+) creation attempts per IP per (\d+)-second fixed window\*\*", README
    )
    assert match is not None
    limit, window = map(int, match.groups())
    limiter = CreationRateLimiter(fake_clock)

    assert (limiter.limit, limiter.window_seconds) == (limit, window) == (5, 60)
    for _ in range(limit):
        assert limiter.check(IP).allowed
    fake_clock.advance(window - 17)
    limited = limiter.check(IP)
    assert limited.retry_after == 17
    assert "`Retry-After: 17`" in README


def test_documented_backoff_schedule_and_cap(fake_clock: FakeClock) -> None:
    match = re.search(r"backoff delays in seconds are\s+`([0-9, ]+)`", README)
    assert match is not None
    documented = [int(value) for value in match.group(1).split(",")]
    backoff = RecipientBackoff(fake_clock)
    actual = []

    for expected in documented:
        actual.append(backoff.record_rejection(IP))
        fake_clock.advance(expected)

    assert actual == documented == [60, 120, 240, 480, 960, 1920, 3600]
    assert backoff.maximum_delay == 3600
    assert backoff.record_rejection(IP) == 3600


def test_documented_trust_and_deployment_constraints_are_explicit() -> None:
    assert "unauthenticated display and filtering label" in README
    assert "including case and whitespace" in README
    assert "questioners = []" in README
    assert "worker-local and reset on restart" in README
    assert "exactly one Klaro instance with exactly one gevent worker" in README
