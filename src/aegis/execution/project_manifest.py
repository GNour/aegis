"""Strict, trusted project manifest.

A project manifest declares the argument-array commands and rootless services a
task worktree may run. Every field is validated closed: unknown keys are rejected
so a project cannot smuggle privileged Docker options, host mounts, or shell
strings past the control plane.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Limits(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    memory_mb: int = Field(ge=64, le=8192)
    cpus: float = Field(gt=0, le=4)


class Service(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    image: str = Field(min_length=1)
    environment: dict[str, str] = Field(default_factory=dict)
    healthcheck: tuple[str, ...]
    container_port: int = Field(ge=1, le=65535)
    limits: Limits

    @field_validator("healthcheck")
    @classmethod
    def nonempty_healthcheck(cls, argv: tuple[str, ...]) -> tuple[str, ...]:
        if not argv or any("\x00" in item for item in argv):
            raise ValueError("healthcheck requires a nonempty NUL-free argument array")
        return argv


class ProjectManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: int = Field(ge=1, le=1)
    commands: dict[str, tuple[str, ...]]
    services: dict[str, Service] = Field(default_factory=dict)
    artifact_globs: tuple[str, ...] = ()

    @field_validator("commands")
    @classmethod
    def nonempty_argv(cls, commands: dict[str, tuple[str, ...]]) -> dict[str, tuple[str, ...]]:
        for name, argv in commands.items():
            if not argv or any("\x00" in item for item in argv):
                raise ValueError(f"command {name!r} requires a nonempty NUL-free argument array")
        return commands


def manifest_json_schema() -> dict[str, Any]:
    """Return the canonical JSON schema committed to config/schemas/project-v1.json."""
    return ProjectManifest.model_json_schema()
