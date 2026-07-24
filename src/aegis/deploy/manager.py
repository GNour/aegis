"""Appliance management surface with authorization tiers.

Read-only operations (status, ps, logs, inspect) may be delegated to the operator group.
Shell, exec, and restart require elevated authorization and emit an audit event. Every
call is scoped to one Compose project through the container runtime.
"""

from collections.abc import Callable
from enum import IntEnum
from typing import Any

from aegis.deploy.runtime import ContainerRuntime
from aegis.execution.command import CommandResult

AuditSink = Callable[[dict[str, Any]], None]


class AuthLevel(IntEnum):
    OPERATOR = 1
    ELEVATED = 2


class ApplianceManager:
    def __init__(
        self, *, runtime: ContainerRuntime, project: str, audit_sink: AuditSink
    ) -> None:
        self._runtime = runtime
        self._project = project
        self._audit = audit_sink

    def _require_elevated(self, authz: AuthLevel, action: str, service: str | None) -> None:
        if authz < AuthLevel.ELEVATED:
            raise PermissionError(f"{action} requires elevated operator authorization")
        self._audit({"action": action, "service": service or "*"})

    # ── read-only (operator group) ───────────────────────────────────────────
    def status(self, *, authz: AuthLevel = AuthLevel.OPERATOR) -> list[dict[str, str]]:
        return self._runtime.ps(self._project)

    def ps(self, *, authz: AuthLevel = AuthLevel.OPERATOR) -> list[dict[str, str]]:
        return self._runtime.ps(self._project)

    def logs(
        self, service: str | None = None, *, authz: AuthLevel = AuthLevel.OPERATOR, follow: bool = False
    ) -> str:
        return self._runtime.logs(self._project, service, follow)

    def inspect(self, service: str, *, authz: AuthLevel = AuthLevel.OPERATOR) -> dict[str, str]:
        return self._runtime.inspect(self._project, service)

    # ── privileged (elevated + audited) ──────────────────────────────────────
    def exec(self, service: str, argv: list[str], *, authz: AuthLevel) -> CommandResult:
        self._require_elevated(authz, "appliance.exec", service)
        return self._runtime.exec(self._project, service, argv)

    def shell(self, service: str, *, authz: AuthLevel) -> CommandResult:
        self._require_elevated(authz, "appliance.shell", service)
        return self._runtime.exec(self._project, service, ["/bin/sh"])

    def restart(self, service: str | None = None, *, authz: AuthLevel) -> None:
        self._require_elevated(authz, "appliance.restart", service)
        self._runtime.restart(self._project, service)
