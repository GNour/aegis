"""Argument-array command execution with structured results.

Every external process the control plane runs goes through :func:`run`. Commands
are always argument arrays (never shell strings), so untrusted values cannot be
interpreted as shell syntax. Results are structured and failures raise a typed
error carrying the captured streams for the audit ledger.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


class CommandError(RuntimeError):
    """A command exited nonzero (or could not be launched)."""

    def __init__(self, result: CommandResult) -> None:
        self.result = result
        super().__init__(
            f"command failed ({result.returncode}): {' '.join(result.argv)}\n{result.stderr}"
        )


def run(
    argv: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
    check: bool = True,
) -> CommandResult:
    """Run ``argv`` and return a structured result. Never uses a shell."""
    if not argv:
        raise ValueError("argv must be nonempty")
    completed = subprocess.run(  # noqa: S603 - argument array, shell disabled
        argv,
        cwd=str(cwd) if cwd is not None else None,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    result = CommandResult(
        argv=tuple(argv),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
    if check and result.returncode != 0:
        raise CommandError(result)
    return result
