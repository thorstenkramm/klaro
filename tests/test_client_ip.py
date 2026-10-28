from __future__ import annotations

import ipaddress

import pytest

from klaro.client_ip import ClientIPResolver


def resolver(*ranges: str) -> ClientIPResolver:
    return ClientIPResolver(ipaddress.ip_network(item, strict=False) for item in ranges)


def test_direct_peer_is_default() -> None:
    assert resolver().resolve("192.0.2.20") == "192.0.2.20"
    assert resolver().resolve("2001:0db8::20") == "2001:db8::20"


@pytest.mark.parametrize("peer", ["192.0.2.20", "2001:db8::20"])
def test_spoofed_forwarding_header_from_untrusted_peer_is_ignored(peer: str) -> None:
    assert resolver("127.0.0.1/32", "10.0.0.0/8", "::1/128").resolve(peer, "198.51.100.99") == str(
        ipaddress.ip_address(peer)
    )


@pytest.mark.parametrize(
    ("peer", "ranges", "forwarded", "expected"),
    [
        ("127.0.0.1", ["127.0.0.1"], "198.51.100.24", "198.51.100.24"),
        ("10.2.3.4", ["10.0.0.0/8"], "198.51.100.25", "198.51.100.25"),
        ("::1", ["::1/128"], "2001:db8::25", "2001:db8::25"),
        ("2001:db8:1::5", ["2001:db8::/32"], "2001:db8:2::25", "2001:db8:2::25"),
    ],
)
def test_trusted_ipv4_and_ipv6_proxies_supply_client(
    peer: str, ranges: list[str], forwarded: str, expected: str
) -> None:
    assert resolver(*ranges).resolve(peer, forwarded) == expected


def test_first_sanitized_forwarded_address_is_used() -> None:
    assert resolver("127.0.0.1").resolve("127.0.0.1", "198.51.100.30, 10.0.0.1") == "198.51.100.30"


@pytest.mark.parametrize("forwarded", [None, "", "not-an-ip", "192.0.2.1:1234"])
def test_invalid_or_missing_forwarded_value_falls_back_to_trusted_peer(
    forwarded: str | None,
) -> None:
    assert resolver("127.0.0.1").resolve("127.0.0.1", forwarded) == "127.0.0.1"
