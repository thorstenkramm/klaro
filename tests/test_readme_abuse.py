from __future__ import annotations

import re
from pathlib import Path

from klaro.abuse import IPV6_CLIENT_PREFIX, CreationRateLimiter, RecipientBackoff, client_key
from tests.helpers import FakeClock

README = (Path(__file__).parent.parent / "README.md").read_text()
IP = "192.0.2.10"


def test_documented_fixed_window_values_and_retry_example(fake_clock: FakeClock) -> None:
    match = re.search(
        r"\*\*(\d+) creation attempts per client per (\d+)-second fixed window\*\*", README
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


def test_documented_client_grouping_and_backoff_expiry(fake_clock: FakeClock) -> None:
    prefix = re.search(r"the /(\d+)\s+network of its IPv6 address", README)
    assert prefix is not None
    assert int(prefix.group(1)) == IPV6_CLIENT_PREFIX
    assert client_key("2001:db8::1") == client_key("2001:db8::ffff") == "2001:db8::/64"
    assert client_key("::ffff:192.0.2.10") == IP
    assert re.search(r"IPv4-mapped IPv6 addresses count\s+as their IPv4 address", README)

    quiet = re.search(r"stays quiet for a further\s+(\d+) seconds after its block ends", README)
    assert quiet is not None
    backoff = RecipientBackoff(fake_clock)
    backoff.record_rejection(IP)
    fake_clock.advance(60 + int(quiet.group(1)))
    assert backoff.record_rejection(IP) == 60


def test_documented_trust_and_deployment_constraints_are_explicit() -> None:
    assert "unauthenticated display and filtering label" in README
    assert "including case and whitespace" in README
    assert "questioners = []" in README
    assert "worker-local and reset on restart" in README
    assert "exactly one Klaro instance with exactly one gevent worker" in README
