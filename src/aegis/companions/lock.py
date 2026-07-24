"""Strict parsing and verification of the admitted companion source pins.

``config/companions.lock.json`` is the canonical record of which companion commits and
built-artifact digests Aegis admits. ``verify_sources`` confirms the installed
submodules match that record exactly and carry no uncommitted changes; anything else
fails closed so a build can never depend on dirty or advanced companion state.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from subprocess import run

from pydantic import BaseModel, ConfigDict, Field

_EXPECTED = {
    "promptx": ("packages/promptx", "https://github.com/GNour/promptx.git"),
    "subagents": ("packages/subagents", "https://github.com/GNour/subagents.git"),
}


class CompanionSourceError(RuntimeError):
    """Raised when a companion submodule is missing, dirty, advanced, or mismatched."""


class GitResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    returncode: int
    stdout: str
    stderr: str


class PackageLock(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    path: str
    source_url: str
    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    package_version: str = Field(
        pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$"
    )
    contract_version: str = Field(pattern=r"^[0-9]+$")
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sbom_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    license_spdx: str = Field(pattern=r"^[A-Za-z0-9-.+]+$")


class CompanionLock(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    schema_version: int = Field(ge=1, le=1)
    promptx: PackageLock
    subagents: PackageLock


def run_git(path: Path, *arguments: str) -> GitResult:
    result = run(
        ["git", "-C", str(path), *arguments],
        check=False,
        capture_output=True,
        text=True,
        shell=False,
    )
    return GitResult(
        returncode=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def verify_sources(
    root: Path,
    lock: CompanionLock,
    *,
    git: Callable[..., GitResult] = run_git,
    require_present: bool = True,
) -> None:
    for name, package in (("promptx", lock.promptx), ("subagents", lock.subagents)):
        if (package.path, package.source_url) != _EXPECTED[name]:
            raise CompanionSourceError(f"{name} path or source URL mismatch")
        path = root / package.path
        if require_present and not path.is_dir():
            raise CompanionSourceError(f"missing companion source: {name}")
        head = git(path, "rev-parse", "HEAD")
        if head.returncode != 0 or head.stdout.strip() != package.source_commit:
            raise CompanionSourceError(f"{name} source commit mismatch")
        status = git(path, "status", "--porcelain", "--untracked-files=all")
        if status.returncode != 0 or status.stdout:
            raise CompanionSourceError(f"dirty companion source: {name}")
