"""Appliance config keeps secrets out and refuses public exposure of private services."""

import pytest

from aegis.deploy.config import ConfigError, validate_config


def _base() -> dict:
    return {
        "version": 1,
        "channel": "stable",
        "services": {"hermes_gateway": True},
        "exposure": {"bind_address": "127.0.0.1"},
        "secrets": {},
    }


def test_inline_secret_value_is_rejected() -> None:
    data = _base()
    data["secrets"] = {"telegram_token": {"source": "file", "ref": "/x", "value": "sk-secret"}}
    with pytest.raises(ConfigError):
        validate_config(data)


def test_public_bind_of_private_service_is_rejected() -> None:
    for addr in ("0.0.0.0", "::", "10.0.0.5", "192.168.1.10"):
        data = _base()
        data["exposure"] = {"bind_address": addr}
        with pytest.raises(ConfigError, match="loopback"):
            validate_config(data)


def test_loopback_binds_are_allowed() -> None:
    for addr in ("127.0.0.1", "::1"):
        data = _base()
        data["exposure"] = {"bind_address": addr}
        assert validate_config(data).exposure.bind_address == addr


def test_nonsecret_digest_excludes_secret_references() -> None:
    a = validate_config({**_base(), "secrets": {"t": {"source": "file", "ref": "/a"}}})
    b = validate_config({**_base(), "secrets": {"t": {"source": "file", "ref": "/b"}}})
    # changing only a secret reference does not change the nonsecret digest
    assert a.nonsecret_digest() == b.nonsecret_digest()


def test_unknown_secret_source_is_rejected() -> None:
    data = _base()
    data["secrets"] = {"t": {"source": "inline", "ref": "x"}}
    with pytest.raises(ConfigError):
        validate_config(data)
