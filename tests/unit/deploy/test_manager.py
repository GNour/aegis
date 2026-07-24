"""The appliance manager enforces authorization tiers and audits privileged ops."""

import pytest

from aegis.deploy.manager import ApplianceManager, AuthLevel
from aegis.deploy.runtime import FakeContainerRuntime


def _manager() -> tuple[ApplianceManager, list, FakeContainerRuntime]:
    runtime = FakeContainerRuntime()
    runtime.seed("aegis", ["aegis-control", "herdr"])
    audit: list = []
    manager = ApplianceManager(runtime=runtime, project="aegis", audit_sink=audit.append)
    return manager, audit, runtime


def test_status_is_readonly_and_needs_only_operator() -> None:
    manager, audit, _ = _manager()
    result = manager.status(authz=AuthLevel.OPERATOR)
    assert "aegis-control" in {row["service"] for row in result}
    assert audit == []


def test_logs_and_inspect_are_readonly() -> None:
    manager, audit, _ = _manager()
    manager.logs("aegis-control", authz=AuthLevel.OPERATOR)
    manager.inspect("aegis-control", authz=AuthLevel.OPERATOR)
    assert audit == []


def test_exec_requires_elevated_authorization() -> None:
    manager, _, _ = _manager()
    with pytest.raises(PermissionError, match="elevated"):
        manager.exec("aegis-control", ["ls"], authz=AuthLevel.OPERATOR)


def test_exec_with_elevated_authorization_is_audited() -> None:
    manager, audit, _ = _manager()
    manager.exec("aegis-control", ["ls"], authz=AuthLevel.ELEVATED)
    assert audit[-1]["action"] == "appliance.exec"
    assert audit[-1]["service"] == "aegis-control"


def test_restart_requires_elevated_and_is_audited() -> None:
    manager, audit, _ = _manager()
    with pytest.raises(PermissionError):
        manager.restart("herdr", authz=AuthLevel.OPERATOR)
    manager.restart("herdr", authz=AuthLevel.ELEVATED)
    assert audit[-1]["action"] == "appliance.restart"


def test_shell_requires_elevated_and_is_audited() -> None:
    manager, audit, _ = _manager()
    with pytest.raises(PermissionError):
        manager.shell("aegis-control", authz=AuthLevel.OPERATOR)
    manager.shell("aegis-control", authz=AuthLevel.ELEVATED)
    assert audit[-1]["action"] == "appliance.shell"


def test_unknown_service_is_rejected() -> None:
    manager, _, _ = _manager()
    with pytest.raises(ValueError, match="unknown service"):
        manager.inspect("ghost", authz=AuthLevel.OPERATOR)
