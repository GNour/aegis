"""Worker specs carry only task-scoped inputs and render sandboxed launch args."""

import pytest
from pydantic import ValidationError

from aegis.execution.sandbox import render_run_args
from aegis.execution.workers import ModelCapability, WorkerSpec, build_worker_spec


@pytest.fixture
def worker_spec() -> WorkerSpec:
    return build_worker_spec(
        task_id="t1",
        runtime="opencode",
        role={"id": "python-dev"},
        capability={"profile": "worktree-write", "memory_mb": 2048, "cpus": 2.0},
        model=ModelCapability(proxy_url="http://model-proxy.internal", capability="implementation"),
        workspace=("/tasks/t1", "/workspace", "rw"),
        skills=[("/skills/s1", "/skills", "ro")],
    )


def test_worker_spec_contains_only_scoped_inputs(worker_spec: WorkerSpec) -> None:
    assert set(worker_spec.environment) == {"AEGIS_TASK_ID", "MODEL_PROXY_URL", "MODEL_CAPABILITY"}
    assert all("OPENAI" not in key and "TOKEN" not in key for key in worker_spec.environment)
    assert worker_spec.network == "none"
    assert worker_spec.mounts == [("/tasks/t1", "/workspace", "rw"), ("/skills/s1", "/skills", "ro")]
    assert worker_spec.cap_drop == ["ALL"]
    assert worker_spec.no_new_privileges is True
    assert worker_spec.read_only_root is True


def test_network_other_than_none_is_rejected() -> None:
    with pytest.raises(ValidationError):
        WorkerSpec(
            task_id="t1",
            image="img",
            argv=["run"],
            environment={},
            mounts=[],
            network="bridge",
            memory_mb=512,
            cpus=1.0,
        )


def test_skill_mount_must_be_read_only() -> None:
    with pytest.raises(ValidationError, match="read-only"):
        WorkerSpec(
            task_id="t1",
            image="img",
            argv=["run"],
            environment={},
            mounts=[("/skills/s1", "/skills", "rw")],
            memory_mb=512,
            cpus=1.0,
        )


def test_mount_source_traversal_is_rejected() -> None:
    with pytest.raises(ValidationError):
        WorkerSpec(
            task_id="t1",
            image="img",
            argv=["run"],
            environment={},
            mounts=[("/tasks/../etc", "/workspace", "rw")],
            memory_mb=512,
            cpus=1.0,
        )


def test_render_run_args_are_sandboxed(worker_spec: WorkerSpec) -> None:
    argv = render_run_args(worker_spec, context="aegis-rootless")
    assert argv[:3] == ["docker", "--context", "aegis-rootless"]
    assert "--network" in argv and "none" in argv
    assert "--cap-drop" in argv and "ALL" in argv
    assert "--security-opt" in argv and "no-new-privileges:true" in argv
    assert "--read-only" in argv
    # environment is passed explicitly; the host environment is never inherited.
    assert "--env-host" not in argv
    joined = " ".join(argv)
    assert "AEGIS_TASK_ID=t1" in joined
    assert argv[-len(worker_spec.argv):] == worker_spec.argv
