"""Task service cleanup removes only exact-identity resources and never prunes."""

import pytest

from aegis.execution.resources import PortAllocator, ResourceIdentity
from aegis.execution.services import FakeServiceRuntime


def test_cleanup_removes_only_matching_identity() -> None:
    runtime = FakeServiceRuntime()
    ours = ResourceIdentity(instance="pilot", task_id="task-a", nonce="n1")
    other = ResourceIdentity(instance="pilot", task_id="task-b", nonce="n2")
    runtime.seed(ours)
    runtime.seed(other)
    runtime.cleanup(ours)
    assert runtime.exists(ours) is False
    assert runtime.exists(other) is True
    assert all("prune" not in argv for argv in runtime.commands)


def test_cleanup_refuses_mismatched_nonce() -> None:
    runtime = FakeServiceRuntime()
    real = ResourceIdentity(instance="pilot", task_id="task-a", nonce="n1")
    runtime.seed(real)
    impostor = ResourceIdentity(instance="pilot", task_id="task-a", nonce="wrong")
    runtime.cleanup(impostor)
    assert runtime.exists(real) is True


def test_identity_labels_include_managed_marker() -> None:
    identity = ResourceIdentity(instance="pilot", task_id="task-a", nonce="n1")
    labels = identity.labels()
    assert labels["dev.aegis.instance"] == "pilot"
    assert labels["dev.aegis.task"] == "task-a"
    assert labels["dev.aegis.nonce"] == "n1"
    assert labels["dev.aegis.managed"] == "true"


def test_compose_project_is_deterministic_and_bounded() -> None:
    identity = ResourceIdentity(
        instance="pilot", task_id="018f8bd9-19d6-7902-9018-593c0a97ea8a", nonce="abcdef1234"
    )
    project = identity.compose_project
    assert project == identity.compose_project
    assert project.startswith("aegis_")
    assert " " not in project


def test_port_allocator_leases_and_releases() -> None:
    allocator = PortAllocator(start=20000, end=20002)
    a = allocator.allocate("task-a", "db")
    b = allocator.allocate("task-a", "cache")
    assert a != b
    assert 20000 <= a <= 20002
    allocator.release("task-a")
    # after release the same ports are available again
    c = allocator.allocate("task-b", "db")
    assert c in {a, b}


def test_port_allocator_exhaustion_raises() -> None:
    allocator = PortAllocator(start=20000, end=20000)
    allocator.allocate("task-a", "db")
    with pytest.raises(RuntimeError, match="no free ports"):
        allocator.allocate("task-a", "cache")
