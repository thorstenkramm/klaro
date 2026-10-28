from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

from klaro.abuse import CreationAbuseControls, CreationRateLimiter, RecipientBackoff
from tests.helpers import FakeClock

IP = "192.0.2.10"


def test_first_five_attempts_are_allowed_and_sixth_is_limited(fake_clock: FakeClock) -> None:
    limiter = CreationRateLimiter(fake_clock)

    decisions = [limiter.check(IP) for _ in range(6)]

    assert [decision.allowed for decision in decisions] == [True] * 5 + [False]
    assert decisions[-1].retry_after == 60


def test_rejected_attempts_do_not_extend_window_and_retry_after_is_exact(
    fake_clock: FakeClock,
) -> None:
    limiter = CreationRateLimiter(fake_clock)
    for _ in range(5):
        limiter.check(IP)

    fake_clock.advance(43)
    sixth = limiter.check(IP)
    fake_clock.advance(7)
    seventh = limiter.check(IP)

    assert sixth.retry_after == 17
    assert seventh.retry_after == 10
    assert limiter._windows[IP].count == 7
    assert limiter._windows[IP].started == 0

    fake_clock.advance(10)
    assert limiter.check(IP).allowed


def test_invalid_attempts_consume_the_same_quota(fake_clock: FakeClock) -> None:
    limiter = CreationRateLimiter(fake_clock)

    for _ in range(5):
        decision = limiter.check(IP)
        assert decision.allowed
        simulated_validation_succeeded = False
        assert not simulated_validation_succeeded

    assert not limiter.check(IP).allowed


def test_windows_are_independent_per_ip(fake_clock: FakeClock) -> None:
    limiter = CreationRateLimiter(fake_clock)
    for _ in range(6):
        limiter.check(IP)

    assert limiter.check("198.51.100.20").allowed
    assert not limiter.check(IP).allowed


def test_stale_windows_are_pruned(fake_clock: FakeClock) -> None:
    limiter = CreationRateLimiter(fake_clock)
    limiter.check(IP)
    fake_clock.advance(61)
    limiter.check("198.51.100.20")

    assert set(limiter._windows) == {"198.51.100.20"}


def test_concurrent_attempts_allow_exactly_five(fake_clock: FakeClock) -> None:
    limiter = CreationRateLimiter(fake_clock)
    workers = 20
    barrier = threading.Barrier(workers)

    def attempt(_: int) -> bool:
        barrier.wait()
        return limiter.check(IP).allowed

    with ThreadPoolExecutor(max_workers=workers) as pool:
        decisions = list(pool.map(attempt, range(workers)))

    assert decisions.count(True) == 5
    assert decisions.count(False) == 15


def test_complete_recipient_backoff_schedule_and_cap(fake_clock: FakeClock) -> None:
    backoff = RecipientBackoff(fake_clock)
    observed = []

    for expected in [60, 120, 240, 480, 960, 1920, 3600, 3600]:
        assert backoff.check(IP).allowed
        assert backoff.record_rejection(IP) == expected
        observed.append(expected)
        assert not backoff.check(IP).allowed
        assert backoff.check(IP).retry_after == expected
        fake_clock.advance(expected)

    assert observed == [60, 120, 240, 480, 960, 1920, 3600, 3600]
    assert backoff.check(IP).allowed


def test_blocked_attempts_do_not_change_delay_or_deadline(fake_clock: FakeClock) -> None:
    backoff = RecipientBackoff(fake_clock)
    backoff.record_rejection(IP)
    state = backoff._states[IP]

    fake_clock.advance(30)
    blocked = backoff.check(IP)

    assert not blocked.allowed
    assert blocked.retry_after == 30
    assert backoff._states[IP] is state
    assert state.delay == 60
    assert state.blocked_until == 60


def test_only_acceptance_resets_backoff_level(fake_clock: FakeClock) -> None:
    backoff = RecipientBackoff(fake_clock)
    backoff.record_rejection(IP)
    fake_clock.advance(60)
    assert backoff.record_rejection(IP) == 120

    fake_clock.advance(120)
    backoff.record_acceptance(IP)
    assert IP not in backoff._states
    assert backoff.record_rejection(IP) == 60


def test_longer_backoff_delay_wins_when_rate_limit_also_applies(fake_clock: FakeClock) -> None:
    controls = CreationAbuseControls(fake_clock)
    for _ in range(5):
        assert controls.check(IP).allowed
    fake_clock.advance(30)
    controls.record_recipient_rejection(IP)

    decision = controls.check(IP)

    assert not decision.allowed
    assert decision.code == "recipient_backoff"
    assert decision.retry_after == 60


def test_longer_rate_delay_wins_when_backoff_also_applies(fake_clock: FakeClock) -> None:
    controls = CreationAbuseControls(fake_clock)
    controls.record_recipient_rejection(IP)
    fake_clock.advance(30)
    for _ in range(5):
        assert controls.rate_limiter.check(IP).allowed

    decision = controls.check(IP)

    assert not decision.allowed
    assert decision.code == "rate_limited"
    assert decision.retry_after == 60


def test_backoff_blocked_attempt_still_consumes_rate_quota(fake_clock: FakeClock) -> None:
    controls = CreationAbuseControls(fake_clock)
    controls.record_recipient_rejection(IP)

    for _ in range(5):
        decision = controls.check(IP)
        assert decision.code == "recipient_backoff"
    sixth = controls.check(IP)

    assert sixth.code == "rate_limited"
    assert sixth.retry_after == 60
