from __future__ import annotations

import configparser
from pathlib import Path

REPOSITORY = Path(__file__).parent.parent
UNIT_PATH = REPOSITORY / "deploy/systemd/klaro.service"
CADDY_PATH = REPOSITORY / "deploy/caddy/Caddyfile"


def unit() -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    with UNIT_PATH.open() as stream:
        parser.read_file(stream)
    return parser


def test_systemd_unit_runs_one_supervised_unprivileged_instance() -> None:
    service = unit()
    expected_service = {
        "Type": "exec",
        "User": "klaro",
        "Group": "klaro",
        "ExecStart": "/opt/klaro/bin/klaro",
        "StateDirectory": "klaro",
        "StateDirectoryMode": "0700",
        "UMask": "0077",
        "Restart": "on-failure",
        "RestartSec": "5s",
        "TimeoutStopSec": "35",
    }
    expected_unit = {"StartLimitIntervalSec": "60", "StartLimitBurst": "5"}

    for key, value in expected_service.items():
        assert service["Service"][key] == value
    for key, value in expected_unit.items():
        assert service["Unit"][key] == value
    assert service["Install"]["WantedBy"] == "multi-user.target"


def test_systemd_unit_has_all_required_hardening() -> None:
    service = unit()["Service"]
    expected = {
        "NoNewPrivileges": "yes",
        "ProtectSystem": "strict",
        "ProtectHome": "yes",
        "PrivateTmp": "yes",
        "PrivateDevices": "yes",
        "ProtectKernelTunables": "yes",
        "ProtectKernelModules": "yes",
        "ProtectKernelLogs": "yes",
        "ProtectControlGroups": "yes",
        "ProtectClock": "yes",
        "ProtectHostname": "yes",
        "RestrictNamespaces": "yes",
        "RestrictRealtime": "yes",
        "RestrictSUIDSGID": "yes",
        "LockPersonality": "yes",
        "MemoryDenyWriteExecute": "yes",
        "RestrictAddressFamilies": "AF_INET AF_INET6 AF_UNIX",
        "CapabilityBoundingSet": "",
        "SystemCallFilter": "@system-service",
    }

    for key, value in expected.items():
        assert service[key] == value


def test_installation_documents_fixed_version_and_restricted_files() -> None:
    from tests.test_operations_docs import operation

    install = operation("release-install")
    assert "useradd -s /usr/sbin/nologin -r -M -d /var/lib/klaro klaro" in install
    assert "releases/download/v0.1.0/klaro-0.1.0.tar.gz" in install
    assert "KLARO_VERSION" not in install
    assert "install -m 0640 -o root -g klaro" in install
    assert "install -d -m 0700 -o klaro -g klaro" in install
    assert "ln -s /opt/klaro/klaro.service" in operation("systemd-service")
    readme = (REPOSITORY / "README.md").read_text()
    for obsolete in (
        "uv tool install",
        "systemd-analyze",
        "Upgrade and roll back a release",
        "host without Internet access",
        "release-attestation",
    ):
        assert obsolete not in readme


def test_caddy_overwrites_client_headers_and_streams_without_buffering() -> None:
    lines = [line.strip() for line in CADDY_PATH.read_text().splitlines()]

    assert lines[0] == "{$KLARO_SITE:klaro.example.com} {"
    assert "reverse_proxy 127.0.0.1:3344 {" in lines
    assert "header_up X-Forwarded-For {remote_host}" in lines
    assert "header_up X-Forwarded-Proto {scheme}" in lines
    assert "flush_interval -1" in lines
    assert any(
        line.startswith("header Strict-Transport-Security ")
        and "max-age=31536000; includeSubDomains" in line
        for line in lines
    )
    assert not any(line == "encode" or line.startswith("encode ") for line in lines)


def test_readme_embeds_shipped_caddyfile_exactly() -> None:
    readme = (REPOSITORY / "README.md").read_text()
    example = readme.split("<!-- example:caddyfile -->", 1)[1]
    block = example.split("```caddyfile\n", 1)[1].split("```", 1)[0]

    assert block == CADDY_PATH.read_text()
    assert 'trusted_proxies = ["127.0.0.1/32"]' in readme
