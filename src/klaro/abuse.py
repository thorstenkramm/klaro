"""Deterministic worker-local abuse controls."""

from __future__ import annotations

import ipaddress
import math
import threading
from dataclasses import dataclass

from klaro.clock import Clock

IPV6_CLIENT_PREFIX = 64


def client_key(client_ip: str) -> str:
    """Return the abuse-control identity of a client address.

    One IPv6 subscriber usually controls a whole /64, so per-address keys would let a
    single host rotate around every limit. IPv4-mapped IPv6 addresses count as IPv4.
    """
    address = ipaddress.ip_address(client_ip)
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return str(address.ipv4_mapped)
        return str(ipaddress.IPv6Network((address, IPV6_CLIENT_PREFIX), strict=False))
    return str(address)


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    retry_after: int = 0


@dataclass(slots=True)
class _Window:
    started: float
    count: int = 0


class CreationRateLimiter:
    """Count every creation attempt in a five-per-60-second fixed window."""

    def __init__(self, clock: Clock, *, limit: int = 5, window_seconds: int = 60) -> None:
        self.clock = clock
        self.limit = limit
        self.window_seconds = window_seconds
        self._windows: dict[str, _Window] = {}
        self._lock = threading.Lock()

    def check(self, client_ip: str) -> RateLimitDecision:
        now = self.clock.monotonic()
        with self._lock:
            stale = [
                ip
                for ip, window in self._windows.items()
                if now - window.started >= self.window_seconds
            ]
            for ip in stale:
                del self._windows[ip]

            window = self._windows.get(client_ip)
            if window is None:
                window = _Window(started=now)
                self._windows[client_ip] = window
            window.count += 1
            if window.count <= self.limit:
                return RateLimitDecision(allowed=True)
            remaining = self.window_seconds - (now - window.started)
            return RateLimitDecision(allowed=False, retry_after=max(1, math.ceil(remaining)))


@dataclass(slots=True)
class _Backoff:
    delay: int
    blocked_until: float


class RecipientBackoff:
    """Track recipient-rejection delays independently from creation rate windows.

    A level is forgotten once a client stays quiet for a full maximum delay after its
    block ends, so rotating clients cannot accumulate state indefinitely.
    """

    def __init__(self, clock: Clock, *, maximum_delay: int = 3600) -> None:
        self.clock = clock
        self.maximum_delay = maximum_delay
        self._states: dict[str, _Backoff] = {}
        self._lock = threading.Lock()

    def _prune(self, now: float) -> None:
        expired = [
            key
            for key, state in self._states.items()
            if now >= state.blocked_until + self.maximum_delay
        ]
        for key in expired:
            del self._states[key]

    def check(self, client_ip: str) -> RateLimitDecision:
        now = self.clock.monotonic()
        with self._lock:
            self._prune(now)
            state = self._states.get(client_ip)
            if state is None or now >= state.blocked_until:
                return RateLimitDecision(allowed=True)
            return RateLimitDecision(
                allowed=False, retry_after=max(1, math.ceil(state.blocked_until - now))
            )

    def record_rejection(self, client_ip: str) -> int:
        now = self.clock.monotonic()
        with self._lock:
            self._prune(now)
            previous = self._states.get(client_ip)
            delay = 60 if previous is None else min(self.maximum_delay, previous.delay * 2)
            self._states[client_ip] = _Backoff(delay=delay, blocked_until=now + delay)
            return delay

    def record_acceptance(self, client_ip: str) -> None:
        with self._lock:
            self._states.pop(client_ip, None)


@dataclass(frozen=True, slots=True)
class AbuseDecision:
    allowed: bool
    code: str | None = None
    retry_after: int = 0


class CreationAbuseControls:
    """Apply both creation controls to the grouped client identity (see ``client_key``)."""

    def __init__(self, clock: Clock) -> None:
        self.rate_limiter = CreationRateLimiter(clock)
        self.recipient_backoff = RecipientBackoff(clock)

    def check(self, client_ip: str) -> AbuseDecision:
        key = client_key(client_ip)
        # The rate check always runs first: even backoff-blocked attempts count.
        rate = self.rate_limiter.check(key)
        backoff = self.recipient_backoff.check(key)
        if rate.allowed and backoff.allowed:
            return AbuseDecision(allowed=True)
        if not rate.allowed and not backoff.allowed:
            if backoff.retry_after > rate.retry_after:
                return AbuseDecision(False, "recipient_backoff", backoff.retry_after)
            return AbuseDecision(False, "rate_limited", rate.retry_after)
        if not rate.allowed:
            return AbuseDecision(False, "rate_limited", rate.retry_after)
        return AbuseDecision(False, "recipient_backoff", backoff.retry_after)

    def record_acceptance(self, client_ip: str) -> None:
        self.recipient_backoff.record_acceptance(client_key(client_ip))

    def record_recipient_rejection(self, client_ip: str) -> int:
        return self.recipient_backoff.record_rejection(client_key(client_ip))
