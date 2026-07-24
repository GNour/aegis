"""The container runtime targets the exact project and never prunes globally."""

from aegis.execution.command import CommandResult
from aegis.deploy.runtime import ComposeContainerRuntime, FakeContainerRuntime


class RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, argv, **kwargs) -> CommandResult:
        self.calls.append(tuple(argv))
        return CommandResult(argv=tuple(argv), returncode=0, stdout="", stderr="")


def _runtime(runner):
    return ComposeContainerRuntime(runner=runner, context="aegis-rootless")


def test_down_targets_exact_project_and_never_prunes() -> None:
    runner = RecordingRunner()
    _runtime(runner).down("aegis")
    joined = [" ".join(call) for call in runner.calls]
    assert any("--project-name aegis" in c and "down" in c for c in joined)
    assert all("prune" not in c for c in joined)
    assert all("--context aegis-rootless" in c for c in joined)


def test_up_uses_project_and_compose_file() -> None:
    runner = RecordingRunner()
    _runtime(runner).up("aegis", "/etc/aegis/compose.yaml")
    argv = runner.calls[-1]
    assert "--project-name" in argv and "aegis" in argv
    assert "-f" in argv and "/etc/aegis/compose.yaml" in argv
    assert "up" in argv


def test_fake_down_removes_only_target_project() -> None:
    runtime = FakeContainerRuntime()
    runtime.seed("aegis", ["aegis-control"])
    runtime.seed("other", ["thing"])
    runtime.down("aegis")
    assert runtime.exists("aegis") is False
    assert runtime.exists("other") is True
    assert all("prune" not in " ".join(cmd) for cmd in runtime.commands)
