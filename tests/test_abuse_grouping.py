"""Abuse controls group IPv6 clients by /64 and forget idle recipient backoff state."""

from __future__ import annotations

import pytest

from klaro.abuse import CreationAbuseControls, RecipientBackoff, client_key
from tests.app_helpers import make_app, post_creation, pushover_response
from tests.helpers import FakeClock


@pytest.mark.parametrize(
    ("address", "key"),
    [
        ("192.0.2.10", "192.0.2.10"),
        ("2001:db8:1:2:3:4:5:6", "2001:db8:1:2::/64"),
        ("2001:db8:1:2:ffff:ffff:ffff:ffff", "2001:db8:1:2::/64"),
        ("2001:db8:1:3::1", "2001:db8:1:3::/64"),
        ("::ffff:192.0.2.10", "192.0.2.10"),
    ],
)
def test_client_key_groups_ipv6_by_64_and_unmaps_ipv4(address: str, key: str) -> None:
    assert client_key(address) == key


def test_rotating_addresses_within_one_ipv6_64_share_the_creation_quota(
    fake_clock: FakeClock,
) -> None:
    controls = CreationAbuseControls(fake_clock)

    decisions = [controls.check(f"2001:db8:1:2::{index:x}") for index in range(1, 7)]

    assert [decision.allowed for decision in decisions] == [True] * 5 + [False]
    assert decisions[-1].code == "rate_limited"
    assert controls.check("2001:db8:1:3::1").allowed


def test_ipv4_mapped_address_shares_the_ipv4_quota(fake_clock: FakeClock) -> None:
    controls = CreationAbuseControls(fake_clock)
    for _ in range(5):
        assert controls.check("192.0.2.10").allowed

    assert not controls.check("::ffff:192.0.2.10").allowed


def test_recipient_backoff_applies_to_the_whole_ipv6_64(fake_clock: FakeClock) -> None:
    controls = CreationAbuseControls(fake_clock)
    controls.check("2001:db8:1:2::1")
    controls.record_recipient_rejection("2001:db8:1:2::1")

    blocked = controls.check("2001:db8:1:2::abcd")

    assert blocked.code == "recipient_backoff"
    assert blocked.retry_after == 60


def test_idle_backoff_state_expires_one_maximum_delay_after_the_block(
    fake_clock: FakeClock,
) -> None:
    backoff = RecipientBackoff(fake_clock)
    assert backoff.record_rejection("192.0.2.10") == 60
    assert backoff.record_rejection("192.0.2.10") == 120

    fake_clock.advance(120 + 3_600 - 1)
    assert "192.0.2.10" in backoff._states
    assert backoff.record_rejection("192.0.2.10") == 240

    fake_clock.advance(240 + 3_600)
    assert backoff.check("192.0.2.10").allowed
    assert backoff._states == {}
    assert backoff.record_rejection("192.0.2.10") == 60


def test_rotating_rejected_clients_do_not_accumulate_backoff_state(
    fake_clock: FakeClock,
) -> None:
    backoff = RecipientBackoff(fake_clock)
    for index in range(100):
        backoff.record_rejection(f"192.0.2.{index}")
        fake_clock.advance(60)

    fake_clock.advance(3_600)
    backoff.check("198.51.100.1")

    assert backoff._states == {}


def test_route_quota_is_shared_by_one_ipv6_64(tmp_path, fake_clock: FakeClock) -> None:
    app, transport = make_app(tmp_path, fake_clock)
    transport.return_value = pushover_response()
    client = app.test_client()

    statuses = [
        post_creation(client, ip=f"2001:db8:1:2::{index:x}").status_code for index in range(1, 7)
    ]

    assert statuses == [201] * 5 + [429]
    assert post_creation(client, ip="2001:db8:9:9::1").status_code == 201
