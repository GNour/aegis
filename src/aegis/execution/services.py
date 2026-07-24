"""Rootless, task-scoped project services with exact-label cleanup.

`ServiceRuntime` is the port the orchestrator calls. `FakeServiceRuntime` gives
tests a deterministic in-memory implementation; `ComposeServiceRuntime` renders an
Aegis-owned Compose project and drives rootless Docker with argument arrays. Every
teardown targets the exact Compose project and verifies our nonce label before
acting — it never runs a global prune and never removes unlabeled resources.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from pathlib import Path

import yaml

from aegis.execution.command import CommandResult, run
from aegis.execution.project_manifest import Service
from aegis.execution.resources import ResourceIdentity

Runner = Callable[..., CommandResult]


class ServiceRuntime(ABC):
    @abstractmethod
    def up(
        self, identity: ResourceIdentity, services: Mapping[str, Service], *, workdir: Path
    ) -> None: ...

    @abstractmethod
    def cleanup(self, identity: ResourceIdentity) -> None: ...


class FakeServiceRuntime(ServiceRuntime):
    """In-memory runtime that records every command verb it was asked to run."""

    def __init__(self) -> None:
        self._resources: dict[str, ResourceIdentity] = {}
        self.commands: list[tuple[str, ...]] = []

    def seed(self, identity: ResourceIdentity) -> None:
        self._resources[identity.compose_project] = identity

    def exists(self, identity: ResourceIdentity) -> bool:
        return identity.compose_project in self._resources

    def up(
        self, identity: ResourceIdentity, services: Mapping[str, Service], *, workdir: Path
    ) -> None:
        self.commands.append(("compose", "up", identity.compose_project))
        self._resources[identity.compose_project] = identity

    def cleanup(self, identity: ResourceIdentity) -> None:
        existing = self._resources.get(identity.compose_project)
        # Refuse unless the recorded identity matches exactly (including nonce).
        if existing is None or existing != identity:
            self.commands.append(("inspect", identity.compose_project))
            return
        self.commands.append(("compose", "down", identity.compose_project))
        del self._resources[identity.compose_project]


class ComposeServiceRuntime(ServiceRuntime):
    def __init__(self, *, runner: Runner = run, context: str = "aegis-rootless") -> None:
        self._run = runner
        self._context = context

    def _compose(self, identity: ResourceIdentity, *args: str) -> list[str]:
        return [
            "docker",
            "--context",
            self._context,
            "compose",
            "--project-name",
            identity.compose_project,
            *args,
        ]

    def _render_override(
        self, identity: ResourceIdentity, services: Mapping[str, Service], workdir: Path
    ) -> Path:
        rendered: dict[str, object] = {
            "name": identity.compose_project,
            "services": {
                name: {
                    "image": service.image,
                    "labels": identity.labels(),
                    "environment": dict(service.environment),
                    "healthcheck": {"test": list(service.healthcheck)},
                    "mem_limit": f"{service.limits.memory_mb}m",
                    "cpus": service.limits.cpus,
                    "read_only": True,
                    "security_opt": ["no-new-privileges:true"],
                    "cap_drop": ["ALL"],
                    "restart": "unless-stopped",
                }
                for name, service in services.items()
            },
        }
        path = workdir / f"{identity.compose_project}.compose.yaml"
        path.write_text(yaml.safe_dump(rendered, sort_keys=True), encoding="utf-8")
        return path

    def up(
        self, identity: ResourceIdentity, services: Mapping[str, Service], *, workdir: Path
    ) -> None:
        override = self._render_override(identity, services, workdir)
        self._run(self._compose(identity, "-f", str(override), "up", "-d", "--wait"))

    def _observed_nonces(self, identity: ResourceIdentity) -> set[str]:
        argv = ["docker", "--context", self._context, "ps", "--all"]
        for selector in identity.label_selectors():
            argv += ["--filter", selector]
        argv += ["--format", '{{index .Labels "dev.aegis.nonce"}}']
        result = self._run(argv, check=False)
        return {line.strip() for line in result.stdout.splitlines() if line.strip()}

    def cleanup(self, identity: ResourceIdentity) -> None:
        observed = self._observed_nonces(identity)
        # Only tear down when every observed resource carries our exact nonce.
        if not observed or observed != {identity.nonce}:
            return
        self._run(self._compose(identity, "down", "--volumes", "--remove-orphans"))
