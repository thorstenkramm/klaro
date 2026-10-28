from __future__ import annotations

import ipaddress
import re
import tomllib
from pathlib import Path

import pytest

from klaro.config import ConfigError, load_config, parse_config


def raw_config(tmp_path: Path) -> dict:
    return {
        "pushover": {"app_token": "a" * 30},
        "klaro": {
            "data_dir": str(tmp_path / "data"),
            "public_address": "https://klaro.example.com/",
        },
    }


def test_minimal_config_applies_defaults(tmp_path: Path) -> None:
    config = parse_config(raw_config(tmp_path))

    assert config.pushover.sound == "pushover"
    assert config.pushover.priority == 0
    assert config.klaro.listen == "127.0.0.1:3344"
    assert config.klaro.lifetime_seconds == 86_400
    assert config.klaro.sse_heartbeat_seconds == 15
    assert config.klaro.questioners is None
    assert config.klaro.trusted_proxies == ()
    assert config.klaro.public_address == "https://klaro.example.com"
    assert config.klaro.data_dir.is_dir()
    assert config.klaro.questionnaire_url("x" * 43) == f"https://klaro.example.com/{'x' * 43}"
    assert "a" * 30 not in repr(config.pushover)


def test_complete_config(tmp_path: Path) -> None:
    raw = raw_config(tmp_path)
    raw["pushover"].update(sound="magic", priority=1)
    raw["klaro"].update(
        listen="[::1]:4444",
        lifetime_seconds=60,
        sse_heartbeat_seconds=5,
        questioners=["Dinner mate"],
        trusted_proxies=["127.0.0.1", "10.0.0.0/8", "::1"],
    )

    config = parse_config(raw)

    assert config.pushover.sound == "magic"
    assert config.pushover.priority == 1
    assert config.klaro.listen == "[::1]:4444"
    assert config.klaro.lifetime_seconds == 60
    assert config.klaro.sse_heartbeat_seconds == 5
    assert config.klaro.questioners == ("Dinner mate",)
    assert config.klaro.trusted_proxies == (
        ipaddress.ip_network("127.0.0.1/32"),
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("::1/128"),
    )


def test_toml_file_and_environment_loading(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "klaro.toml"
    path.write_text(
        f"""[pushover]
app_token = "{"b" * 30}"

[klaro]
data_dir = "{tmp_path / "data"}"
public_address = "https://klaro.example.com"
"""
    )

    assert load_config(path).pushover.app_token == "b" * 30
    monkeypatch.setenv("KLARO_CONFIG", str(path))
    assert load_config().klaro.public_address == "https://klaro.example.com"


@pytest.mark.parametrize(
    ("section", "field"),
    [("pushover", "app_token"), ("klaro", "data_dir"), ("klaro", "public_address")],
)
def test_mandatory_fields(tmp_path: Path, section: str, field: str) -> None:
    raw = raw_config(tmp_path)
    del raw[section][field]
    with pytest.raises(ConfigError, match=field):
        parse_config(raw)


@pytest.mark.parametrize("token", ["short", "x" * 31, "x" * 29 + "-", 123, "x" * 29 + "ä"])
def test_app_token_validation(tmp_path: Path, token: object) -> None:
    raw = raw_config(tmp_path)
    raw["pushover"]["app_token"] = token
    with pytest.raises(ConfigError):
        parse_config(raw)


@pytest.mark.parametrize("priority", [-2, -1, 0, 1])
def test_supported_priorities(tmp_path: Path, priority: int) -> None:
    raw = raw_config(tmp_path)
    raw["pushover"]["priority"] = priority
    assert parse_config(raw).pushover.priority == priority


@pytest.mark.parametrize("priority", [-3, 2, True, 0.5, "0"])
def test_invalid_priorities(tmp_path: Path, priority: object) -> None:
    raw = raw_config(tmp_path)
    raw["pushover"]["priority"] = priority
    with pytest.raises(ConfigError, match="priority"):
        parse_config(raw)


@pytest.mark.parametrize("field", ["lifetime_seconds", "sse_heartbeat_seconds"])
@pytest.mark.parametrize("value", [0, -1, True, 1.5, "15"])
def test_positive_intervals(tmp_path: Path, field: str, value: object) -> None:
    raw = raw_config(tmp_path)
    raw["klaro"][field] = value
    with pytest.raises(ConfigError, match=field):
        parse_config(raw)


@pytest.mark.parametrize(
    "address",
    [
        "klaro.example.com",
        "ftp://example.com",
        "https://example.com?q=1",
        "https://example.com/#x",
        "https://example.com/" + "x" * 500,
    ],
)
def test_public_address_validation(tmp_path: Path, address: str) -> None:
    raw = raw_config(tmp_path)
    raw["klaro"]["public_address"] = address
    with pytest.raises(ConfigError, match="public_address"):
        parse_config(raw)


@pytest.mark.parametrize(
    "listen", ["localhost", "localhost:not-a-port", "http://localhost:33", ":3344"]
)
def test_listen_validation(tmp_path: Path, listen: str) -> None:
    raw = raw_config(tmp_path)
    raw["klaro"]["listen"] = listen
    with pytest.raises(ConfigError, match="listen"):
        parse_config(raw)


def test_questioner_semantics(tmp_path: Path) -> None:
    raw = raw_config(tmp_path)
    raw["klaro"]["questioners"] = []
    assert parse_config(raw).klaro.questioners == ()
    raw["klaro"]["questioners"] = "anybody"
    with pytest.raises(ConfigError, match="questioners"):
        parse_config(raw)
    raw["klaro"]["questioners"] = [" "]
    with pytest.raises(ConfigError, match="questioners"):
        parse_config(raw)


def test_proxy_validation(tmp_path: Path) -> None:
    raw = raw_config(tmp_path)
    raw["klaro"]["trusted_proxies"] = ["not-an-ip"]
    with pytest.raises(ConfigError, match="trusted_proxies"):
        parse_config(raw)


def test_data_dir_must_be_directory(tmp_path: Path) -> None:
    path = tmp_path / "data"
    path.write_text("not a directory")
    raw = raw_config(tmp_path)
    raw["klaro"]["data_dir"] = str(path)
    with pytest.raises(ConfigError, match="data_dir"):
        parse_config(raw)


def test_unknown_fields_are_errors(tmp_path: Path) -> None:
    raw = raw_config(tmp_path)
    raw["klaro"]["surprise"] = True
    with pytest.raises(ConfigError, match="surprise"):
        parse_config(raw)


def test_missing_or_malformed_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="Cannot load"):
        load_config(tmp_path / "missing.toml")
    path = tmp_path / "bad.toml"
    path.write_text("[not-valid")
    with pytest.raises(ConfigError, match="Cannot load"):
        load_config(path)


def test_readme_complete_example_and_defaults(tmp_path: Path) -> None:
    readme = (Path(__file__).parent.parent / "README.md").read_text()
    blocks = re.findall(r"```toml\n(.*?)```", readme, re.DOTALL)
    assert len(blocks) == 1
    raw = tomllib.loads(blocks[0])
    raw["klaro"]["data_dir"] = str(tmp_path / "data")

    config = parse_config(raw)

    assert config.pushover.sound == "pushover"
    assert config.pushover.priority == 0
    assert config.klaro.listen == "127.0.0.1:3344"
    assert config.klaro.lifetime_seconds == 86_400
    assert config.klaro.sse_heartbeat_seconds == 15
    assert config.klaro.questioners is None
    assert config.klaro.trusted_proxies == ()
