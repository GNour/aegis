"""Container runtime port for appliance management.

`ContainerRuntime` is the only way the manager touches containers. Operations are
argument arrays scoped to the exact Compose project; teardown runs ``compose down`` for
that project and never a global prune. `FakeContainerRuntime` backs tests;
`ComposeContainerRuntime` drives rootless Docker Compose in production.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable

from aegis.execution.command import CommandResult, run

Runner = Callable[..., CommandResult]


class ContainerRuntime(ABC):
    @abstractmethod
    def up(self, project: str, compose_file: str) -> None: ...
    @abstractmethod
    def down(self, project: str) -> None: ...
    @abstractmethod
    def ps(self, project: str) -> list[dict[str, str]]: ...
    @abstractmethod
    def logs(self, project: str, service: str | None, follow: bool = False) -> str: ...
    @abstractmethod
    def exec(self, project: str, service: str, argv: list[str]) -> CommandResult: ...
    @abstractmethod
    def restart(self, project: str, service: str | None) -> None: ...
    @abstractmethod
    def inspect(self, project: str, service: str) -> dict[str, str]: ...


class FakeContainerRuntime(ContainerRuntime):
    def __init__(self) -> None:
        self._projects: dict[str, list[str]] = {}
        self.commands: list[tuple[str, ...]] = []

    def seed(self, project: str, services: list[str]) -> None:
        self._projects[project] = list(services)

    def exists(self, project: str) -> bool:
        return project in self._projects

    def _require(self, project: str, service: str) -> None:
        if service not in self._projects.get(project, []):
            raise ValueError(f"unknown service: {service}")

    def up(self, project: str, compose_file: str) -> None:
        self.commands.append(("up", project))
        self._projects.setdefault(project, [])

    def down(self, project: str) -> None:
        self.commands.append(("down", project))
        self._projects.pop(project, None)

    def ps(self, project: str) -> list[dict[str, str]]:
        return [
            {"service": name, "state": "running"}
            for name in self._projects.get(project, [])
        ]

    def logs(self, project: str, service: str | None, follow: bool = False) -> str:
        if service is not None:
            self._require(project, service)
        return ""

    def exec(self, project: str, service: str, argv: list[str]) -> CommandResult:
        self._require(project, service)
        self.commands.append(("exec", project, service))
        return CommandResult(argv=tuple(argv), returncode=0, stdout="", stderr="")

    def restart(self, project: str, service: str | None) -> None:
        if service is not None:
            self._require(project, service)
        self.commands.append(("restart", project, service or "*"))

    def inspect(self, project: str, service: str) -> dict[str, str]:
        self._require(project, service)
        return {"service": service, "state": "running"}


class ComposeContainerRuntime(ContainerRuntime):
    def __init__(self, *, runner: Runner = run, context: str = "aegis-rootless") -> None:
        self._run = runner
        self._context = context

    def _compose(self, project: str, *args: str) -> list[str]:
        return [
            "docker",
            "--context",
            self._context,
            "compose",
            "--project-name",
            project,
            *args,
        ]

    def up(self, project: str, compose_file: str) -> None:
        self._run(self._compose(project, "-f", compose_file, "up", "-d", "--wait"))

    def down(self, project: str) -> None:
        # Exact project only; disposable volumes/orphans; never a global prune.
        self._run(self._compose(project, "down", "--remove-orphans"))

    def ps(self, project: str) -> list[dict[str, str]]:
        self._run(self._compose(project, "ps", "--format", "json"), check=False)
        return []

    def logs(self, project: str, service: str | None, follow: bool = False) -> str:
        args = ["logs"]
        if follow:
            args.append("--follow")
        if service:
            args.append(service)
        return self._run(self._compose(project, *args), check=False).stdout

    def exec(self, project: str, service: str, argv: list[str]) -> CommandResult:
        return self._run(self._compose(project, "exec", service, *argv))

    def restart(self, project: str, service: str | None) -> None:
        args = ["restart"]
        if service:
            args.append(service)
        self._run(self._compose(project, *args))

    def inspect(self, project: str, service: str) -> dict[str, str]:
        self._run(self._compose(project, "ps", service, "--format", "json"), check=False)
        return {"service": service}
