"""Versioned, schema-validated appliance configuration.

The configuration is validated closed (`extra="forbid"`) and carries only secret
*references* — never secret values. Private services may bind only loopback endpoints;
a public bind is rejected. The nonsecret digest excludes the secrets section entirely so
it can be recorded and compared without exposing (or being perturbed by) secret material.
"""

import hashlib
import ipaddress
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class ConfigError(ValueError):
    """Raised when an appliance configuration fails validation."""


class SecretRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source: Literal["file", "env", "provider"]
    ref: str = Field(min_length=1)


class ServiceToggles(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    hermes_gateway: bool = False
    qmd: bool = True
    openviking: bool = True


class Exposure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    bind_address: str = "127.0.0.1"

    @field_validator("bind_address")
    @classmethod
    def must_be_loopback(cls, value: str) -> str:
        try:
            address = ipaddress.ip_address(value)
        except ValueError as error:
            raise ValueError("bind_address must be a loopback IP address") from error
        if not address.is_loopback:
            raise ValueError("private services may bind only a loopback address")
        return value


class ApplianceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: int = Field(ge=1, le=1)
    channel: Literal["stable", "edge"] = "stable"
    services: ServiceToggles = Field(default_factory=ServiceToggles)
    exposure: Exposure = Field(default_factory=Exposure)
    secrets: dict[str, SecretRef] = Field(default_factory=dict)

    def nonsecret_digest(self) -> str:
        payload = self.model_dump(mode="json")
        payload.pop("secrets", None)
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def init_config(**overrides: Any) -> ApplianceConfig:
    """Return a default configuration, applying any provided overrides."""
    return validate_config({"version": 1, **overrides})


def validate_config(data: dict[str, Any]) -> ApplianceConfig:
    try:
        return ApplianceConfig.model_validate(data)
    except ValidationError as error:
        raise ConfigError(str(error)) from error


def diff_config(a: ApplianceConfig, b: ApplianceConfig) -> dict[str, tuple[Any, Any]]:
    left = a.model_dump(mode="json")
    right = b.model_dump(mode="json")
    changed: dict[str, tuple[Any, Any]] = {}
    for key in sorted(set(left) | set(right)):
        if left.get(key) != right.get(key):
            changed[key] = (left.get(key), right.get(key))
    return changed


def appliance_json_schema() -> dict[str, Any]:
    return ApplianceConfig.model_json_schema()
