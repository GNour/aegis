"""The appliance configuration is versioned, validated, and diffable."""

import json
from pathlib import Path

import pytest

from aegis.deploy.config import (
    ConfigError,
    appliance_json_schema,
    diff_config,
    init_config,
    validate_config,
)

_SCHEMA = Path(__file__).resolve().parents[3] / "config" / "schemas" / "appliance-v1.json"


def _valid() -> dict:
    return {
        "version": 1,
        "channel": "stable",
        "services": {"hermes_gateway": True},
        "exposure": {"bind_address": "127.0.0.1"},
        "secrets": {"telegram_token": {"source": "file", "ref": "/etc/aegis/secrets/tg"}},
    }


def test_default_config_validates() -> None:
    config = init_config()
    assert config.version == 1
    assert config.channel == "stable"


def test_valid_config_round_trips() -> None:
    config = validate_config(_valid())
    assert config.services.hermes_gateway is True
    assert config.secrets["telegram_token"].source == "file"


def test_unknown_key_is_rejected() -> None:
    data = {**_valid(), "danger": True}
    with pytest.raises(ConfigError):
        validate_config(data)


def test_unsupported_version_is_rejected() -> None:
    with pytest.raises(ConfigError):
        validate_config({**_valid(), "version": 2})


def test_diff_reports_changes() -> None:
    a = validate_config(_valid())
    b = validate_config({**_valid(), "channel": "edge"})
    diff = diff_config(a, b)
    assert "channel" in diff
    assert diff["channel"] == ("stable", "edge")


def test_nonsecret_digest_is_stable() -> None:
    a = validate_config(_valid())
    b = validate_config(_valid())
    assert a.nonsecret_digest() == b.nonsecret_digest()


def test_committed_schema_matches_generated() -> None:
    committed = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    assert committed == appliance_json_schema()


def test_config_is_frozen() -> None:
    config = validate_config(_valid())
    with pytest.raises(Exception):
        config.version = 2  # type: ignore[misc]
