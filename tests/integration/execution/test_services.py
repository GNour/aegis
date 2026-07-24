"""ComposeServiceRuntime renders exact-project rootless commands and never prunes."""

from aegis.execution.command import CommandResult
from aegis.execution.project_manifest import Service
from aegis.execution.resources import ResourceIdentity


class RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.responses: dict[str, str] = {}

    def __call__(self, argv, **kwargs) -> CommandResult:
        self.calls.append(tuple(argv))
        key = " ".join(argv)
        stdout = ""
        for needle, value in self.responses.items():
            if needle in key:
                stdout = value
        return CommandResult(argv=tuple(argv), returncode=0, stdout=stdout, stderr="")


def _service() -> Service:
    return Service.model_validate(
        {
            "image": "postgres:17",
            "healthcheck": ["pg_isready"],
            "container_port": 5432,
            "limits": {"memory_mb": 512, "cpus": 1.0},
        }
    )


def _runtime(runner):
    from aegis.execution.services import ComposeServiceRuntime

    return ComposeServiceRuntime(runner=runner, context="aegis-rootless")


def test_up_uses_exact_project_name_and_rootless_context(tmp_path) -> None:
    runner = RecordingRunner()
    identity = ResourceIdentity(instance="pilot", task_id="task-a", nonce="n1")
    _runtime(runner).up(identity, {"db": _service()}, workdir=tmp_path)

    up_calls = [c for c in runner.calls if "up" in c]
    assert up_calls, "expected a compose up call"
    argv = up_calls[0]
    assert "--context" in argv and "aegis-rootless" in argv
    assert "--project-name" in argv
    assert identity.compose_project in argv
    assert "--wait" in argv


def test_cleanup_targets_exact_project_and_never_prunes(tmp_path) -> None:
    runner = RecordingRunner()
    identity = ResourceIdentity(instance="pilot", task_id="task-a", nonce="n1")
    # ps by-label lookup reports our container carrying the exact nonce label.
    runner.responses["ps"] = identity.nonce + "\n"
    _runtime(runner).cleanup(identity)

    joined = [" ".join(c) for c in runner.calls]
    assert any("down" in c and "--volumes" in c and "--remove-orphans" in c for c in joined)
    assert any(identity.compose_project in c for c in joined)
    assert all("prune" not in c for c in joined)


def test_cleanup_refuses_when_labels_do_not_match(tmp_path) -> None:
    runner = RecordingRunner()
    identity = ResourceIdentity(instance="pilot", task_id="task-a", nonce="n1")
    # ps reports a different nonce -> not ours, refuse to tear down.
    runner.responses["ps"] = "someone-elses-nonce\n"
    _runtime(runner).cleanup(identity)

    joined = [" ".join(c) for c in runner.calls]
    assert all("down" not in c for c in joined)
