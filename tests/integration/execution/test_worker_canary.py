"""A seeded provider credential in the parent process never reaches a worker.

Herdr/Docker are not available here, so instead of launching a container this test
builds the worker specification and rendered launch arguments -- the entire surface
the control plane hands to the runtime -- and proves a canary provider key present
in the parent environment appears in none of it.
"""

import pytest

from aegis.execution.sandbox import render_run_args, scan_for_canary
from aegis.execution.workers import ModelCapability, WorkerSpec, build_worker_spec

CANARY = "sk-canary-DO-NOT-LEAK-0123456789"


@pytest.fixture
def _seed_canary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", CANARY)
    monkeypatch.setenv("ANTHROPIC_API_KEY", CANARY)
    monkeypatch.setenv("AEGIS_SIGNING_SECRET", CANARY)


def _spec() -> WorkerSpec:
    return build_worker_spec(
        task_id="t1",
        runtime="opencode",
        role={"id": "python-dev"},
        capability={"profile": "worktree-write", "memory_mb": 2048, "cpus": 2.0},
        model=ModelCapability(proxy_url="http://model-proxy.internal", capability="implementation"),
        workspace=("/tasks/t1", "/workspace", "rw"),
        skills=[("/skills/s1", "/skills", "ro")],
    )


@pytest.mark.usefixtures("_seed_canary")
def test_canary_absent_from_spec_and_launch_surface() -> None:
    spec = _spec()
    surface = [
        *spec.environment.values(),
        *spec.environment.keys(),
        *spec.argv,
        *[part for mount in spec.mounts for part in mount],
        " ".join(render_run_args(spec, context="aegis-rootless")),
    ]
    assert scan_for_canary(surface, CANARY) == []


@pytest.mark.usefixtures("_seed_canary")
def test_network_probe_fails_closed() -> None:
    spec = _spec()
    argv = render_run_args(spec, context="aegis-rootless")
    idx = argv.index("--network")
    assert argv[idx + 1] == "none"


def test_scan_for_canary_detects_a_leak() -> None:
    # Sanity: the scanner is not vacuously passing.
    assert scan_for_canary(["prefix " + CANARY + " suffix"], CANARY) == ["prefix ... suffix"]
