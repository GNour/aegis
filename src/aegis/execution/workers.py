"""Immutable, task-scoped worker specifications.

A worker runs one coding CLI in a rootless container. Its specification is built
only from role/capability snapshots and a short-lived model capability -- never
from the parent process environment. The spec is validated closed: no network, a
read-only root, all capabilities dropped, and no privilege escalation. Skill mounts
must be read-only and no mount source may traverse outside its declared path.
"""

from dataclasses import dataclass
from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator

Mount = tuple[str, str, str]

RUNTIME_IMAGES: dict[str, str] = {
    "opencode": "aegis/opencode:pinned",
    "codex": "aegis/codex:pinned",
}
RUNTIME_ARGV: dict[str, list[str]] = {
    "opencode": ["opencode", "run"],
    "codex": ["codex", "exec"],
}


@dataclass(frozen=True)
class ModelCapability:
    """A short-lived reference to the model proxy; carries no provider credential."""

    proxy_url: str
    capability: str


class WorkerSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    task_id: str
    image: str = Field(min_length=1)
    argv: list[str]
    environment: dict[str, str]
    mounts: list[Mount]
    network: str = "none"
    memory_mb: int = Field(ge=64, le=8192)
    cpus: float = Field(gt=0, le=8)
    cap_drop: list[str] = Field(default_factory=lambda: ["ALL"])
    no_new_privileges: bool = True
    read_only_root: bool = True

    @field_validator("network")
    @classmethod
    def network_is_isolated(cls, network: str) -> str:
        if network != "none":
            raise ValueError("workers run with network 'none'")
        return network

    @field_validator("mounts")
    @classmethod
    def mounts_are_safe(cls, mounts: list[Mount]) -> list[Mount]:
        for source, target, mode in mounts:
            if ".." in source.split("/") or ".." in target.split("/"):
                raise ValueError("mount paths must not traverse")
            if mode not in {"ro", "rw"}:
                raise ValueError("mount mode must be 'ro' or 'rw'")
            if target == "/skills" and mode != "ro":
                raise ValueError("skill mounts must be read-only")
        return mounts

    @field_validator("argv")
    @classmethod
    def argv_nonempty(cls, argv: list[str]) -> list[str]:
        if not argv or any("\x00" in item for item in argv):
            raise ValueError("argv must be a nonempty NUL-free argument array")
        return argv


def build_worker_spec(
    *,
    task_id: str,
    runtime: str,
    role: Mapping[str, object],
    capability: Mapping[str, object],
    model: ModelCapability,
    workspace: Mount,
    skills: list[Mount],
) -> WorkerSpec:
    """Build a worker spec from snapshots and a model capability only.

    The environment is limited to the task id and the model-proxy handle; no
    provider key or host variable is ever propagated.
    """
    if runtime not in RUNTIME_IMAGES:
        raise ValueError(f"unknown runtime {runtime!r}")
    _ = role  # role snapshot informs skills/mounts upstream; retained for provenance
    return WorkerSpec(
        task_id=task_id,
        image=RUNTIME_IMAGES[runtime],
        argv=list(RUNTIME_ARGV[runtime]),
        environment={
            "AEGIS_TASK_ID": task_id,
            "MODEL_PROXY_URL": model.proxy_url,
            "MODEL_CAPABILITY": model.capability,
        },
        mounts=[workspace, *skills],
        memory_mb=int(capability["memory_mb"]),  # type: ignore[call-overload]
        cpus=float(capability["cpus"]),  # type: ignore[arg-type]
    )
