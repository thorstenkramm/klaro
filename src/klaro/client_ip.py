"""Resolve creation client addresses without trusting spoofable headers."""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable


class ClientIPResolver:
    def __init__(
        self,
        trusted_proxies: Iterable[ipaddress.IPv4Network | ipaddress.IPv6Network] = (),
    ) -> None:
        self.trusted_proxies = tuple(trusted_proxies)

    def resolve(self, remote_addr: str, forwarded_for: str | None = None) -> str:
        peer = ipaddress.ip_address(remote_addr)
        trusted = any(peer in network for network in self.trusted_proxies)
        if not trusted or not forwarded_for:
            return str(peer)

        # A trusted proxy is required to overwrite this header. Taking the first
        # entry also supports a sanitized multi-proxy chain's original client.
        candidate = forwarded_for.split(",", 1)[0].strip()
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            return str(peer)
