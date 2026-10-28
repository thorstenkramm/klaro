"""TOML configuration loading and startup validation."""

from __future__ import annotations

import ipaddress
import os
import re
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

DEFAULT_LIFETIME_SECONDS = 86_400
_TOKEN_RE = re.compile(r"^[A-Za-z0-9]{30}$", re.ASCII)
_TOKEN_URL_LENGTH = 43
_MAX_PUSHOVER_URL = 512


class ConfigError(ValueError):
    """Raised when Klaro cannot start with the supplied configuration."""


@dataclass(frozen=True, slots=True)
class PushoverConfig:
    app_token: str = field(repr=False)
    sound: str = "pushover"
    priority: int = 0


@dataclass(frozen=True, slots=True)
class KlaroConfig:
    data_dir: Path
    public_address: str
    listen: str = "127.0.0.1:3344"
    lifetime_seconds: int = DEFAULT_LIFETIME_SECONDS
    sse_heartbeat_seconds: int = 15
    questioners: tuple[str, ...] | None = None
    trusted_proxies: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = ()

    def questionnaire_url(self, token: str) -> str:
        return f"{self.public_address}/{token}"


@dataclass(frozen=True, slots=True)
class Config:
    pushover: PushoverConfig
    klaro: KlaroConfig


def _table(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"[{name}] must be a TOML table")
    return value


def _known_fields(raw: dict[str, Any], allowed: set[str], name: str) -> None:
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ConfigError(f"Unknown field(s) in [{name}]: {', '.join(unknown)}")


def _string(value: Any, name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ConfigError(f"{name} must be a non-empty string")
    return value


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigError(f"{name} must be a positive integer")
    return int(value)


def _validate_listen(value: str) -> str:
    error = ConfigError("klaro.listen must be a host:port address")
    try:
        parsed = urlsplit(f"//{value}")
        port = parsed.port
    except ValueError as exc:  # Out-of-range or non-numeric port
        raise error from exc
    if not parsed.hostname or port is None or parsed.path:
        raise error
    return value


def _validate_public_address(value: str) -> str:
    address = value.rstrip("/")
    parsed = urlsplit(address)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigError("klaro.public_address must be an absolute HTTP(S) URL")
    if parsed.query or parsed.fragment:
        raise ConfigError("klaro.public_address must not contain a query or fragment")
    if parsed.path:
        # Routes, redirects, form actions, and assets are all served from the root.
        raise ConfigError(
            "klaro.public_address must not contain a path; serve Klaro from the root "
            "of its own host name"
        )
    if len(address) + 1 + _TOKEN_URL_LENGTH > _MAX_PUSHOVER_URL:
        raise ConfigError("klaro.public_address is too long for Pushover supplementary URLs")
    return address


def _prepare_data_dir(value: Any) -> Path:
    path = Path(_string(value, "klaro.data_dir")).expanduser()
    not_writable = ConfigError(f"klaro.data_dir is not writable: {path}")
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as exc:
        raise not_writable from exc
    if not path.is_dir():
        raise ConfigError("klaro.data_dir must name a directory")
    try:
        with tempfile.TemporaryFile(prefix=".write-test-", dir=path):
            pass
    except OSError as exc:
        raise not_writable from exc
    return path


def _questioners(value: Any) -> tuple[str, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ConfigError("klaro.questioners must be an array of strings")
    result: list[str] = []
    for index, item in enumerate(value):
        label = _string(item, f"klaro.questioners[{index}]")
        if len(label) > 100:
            raise ConfigError(f"klaro.questioners[{index}] must contain at most 100 characters")
        result.append(label)
    return tuple(result)


def _trusted_proxies(value: Any) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ConfigError("klaro.trusted_proxies must be an array of IP addresses or CIDR ranges")
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for index, item in enumerate(value):
        try:
            networks.append(
                ipaddress.ip_network(_string(item, f"klaro.trusted_proxies[{index}]"), strict=False)
            )
        except ValueError as exc:
            raise ConfigError(f"Invalid klaro.trusted_proxies[{index}]: {item!r}") from exc
    return tuple(networks)


def parse_config(raw: dict[str, Any]) -> Config:
    """Validate an already-decoded configuration mapping."""
    _known_fields(raw, {"pushover", "klaro"}, "root")
    pushover_raw = _table(raw.get("pushover"), "pushover")
    klaro_raw = _table(raw.get("klaro"), "klaro")
    _known_fields(pushover_raw, {"app_token", "sound", "priority"}, "pushover")
    _known_fields(
        klaro_raw,
        {
            "data_dir",
            "public_address",
            "listen",
            "lifetime_seconds",
            "sse_heartbeat_seconds",
            "questioners",
            "trusted_proxies",
        },
        "klaro",
    )

    app_token = _string(pushover_raw.get("app_token"), "pushover.app_token")
    if not _TOKEN_RE.fullmatch(app_token):
        raise ConfigError(
            "pushover.app_token must contain exactly 30 ASCII alphanumeric characters"
        )
    sound = _string(pushover_raw.get("sound", "pushover"), "pushover.sound")
    priority = pushover_raw.get("priority", 0)
    if isinstance(priority, bool) or not isinstance(priority, int) or not -2 <= priority <= 1:
        raise ConfigError("pushover.priority must be an integer from -2 through 1")

    data_dir = _prepare_data_dir(klaro_raw.get("data_dir"))
    public_address = _validate_public_address(
        _string(klaro_raw.get("public_address"), "klaro.public_address")
    )
    listen = _validate_listen(_string(klaro_raw.get("listen", "127.0.0.1:3344"), "klaro.listen"))
    lifetime = _positive_int(
        klaro_raw.get("lifetime_seconds", DEFAULT_LIFETIME_SECONDS), "klaro.lifetime_seconds"
    )
    heartbeat = _positive_int(
        klaro_raw.get("sse_heartbeat_seconds", 15), "klaro.sse_heartbeat_seconds"
    )

    return Config(
        pushover=PushoverConfig(app_token=app_token, sound=sound, priority=priority),
        klaro=KlaroConfig(
            data_dir=data_dir,
            public_address=public_address,
            listen=listen,
            lifetime_seconds=lifetime,
            sse_heartbeat_seconds=heartbeat,
            questioners=_questioners(klaro_raw.get("questioners")),
            trusted_proxies=_trusted_proxies(klaro_raw.get("trusted_proxies")),
        ),
    )


def load_config(path: str | os.PathLike[str] | None = None) -> Config:
    """Load TOML from path, or from KLARO_CONFIG when path is omitted."""
    selected = path or os.environ.get("KLARO_CONFIG")
    if not selected:
        raise ConfigError("Set KLARO_CONFIG or pass a configuration file path")
    config_path = Path(selected)
    try:
        with config_path.open("rb") as handle:
            raw = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"Cannot load configuration from {config_path}: {exc}") from exc
    return parse_config(raw)
