from pathlib import Path

import pytest

from aegis.companions.lock import (
    CompanionLock,
    CompanionSourceError,
    GitResult,
    verify_sources,
)


def admitted_lock() -> CompanionLock:
    return CompanionLock.model_validate(
        {
            "schema_version": 1,
            "promptx": {
                "path": "packages/promptx",
                "source_url": "https://github.com/GNour/promptx.git",
                "source_commit": "a" * 40,
                "package_version": "1.0.0",
                "contract_version": "1",
                "artifact_sha256": "1" * 64,
                "sbom_sha256": "3" * 64,
                "license_spdx": "MIT",
            },
            "subagents": {
                "path": "packages/subagents",
                "source_url": "https://github.com/GNour/subagents.git",
                "source_commit": "b" * 40,
                "package_version": "1.0.0",
                "contract_version": "1",
                "artifact_sha256": "2" * 64,
                "sbom_sha256": "4" * 64,
                "license_spdx": "MIT",
            },
        }
    )


def test_clean_exact_sources_are_accepted(tmp_path: Path) -> None:
    lock = admitted_lock()

    def git(path: Path, *arguments: str) -> GitResult:
        if arguments == ("rev-parse", "HEAD"):
            commit = (
                lock.promptx.source_commit
                if path.name == "promptx"
                else lock.subagents.source_commit
            )
            return GitResult(returncode=0, stdout=commit + "\n", stderr="")
        if arguments == ("status", "--porcelain", "--untracked-files=all"):
            return GitResult(returncode=0, stdout="", stderr="")
        raise AssertionError(arguments)

    verify_sources(tmp_path, lock, git=git, require_present=False)


@pytest.mark.parametrize(
    ("head", "status", "message"),
    [
        ("c" * 40, "", "source commit mismatch"),
        ("a" * 40, " M package.json\n", "dirty companion source"),
    ],
)
def test_promptx_advanced_or_dirty_source_is_rejected(
    tmp_path: Path, head: str, status: str, message: str
) -> None:
    lock = admitted_lock()

    def git(path: Path, *arguments: str) -> GitResult:
        if path.name == "promptx" and arguments == ("rev-parse", "HEAD"):
            return GitResult(returncode=0, stdout=head + "\n", stderr="")
        if path.name == "subagents" and arguments == ("rev-parse", "HEAD"):
            return GitResult(
                returncode=0,
                stdout=lock.subagents.source_commit + "\n",
                stderr="",
            )
        if arguments == ("status", "--porcelain", "--untracked-files=all"):
            return GitResult(
                returncode=0,
                stdout=status if path.name == "promptx" else "",
                stderr="",
            )
        raise AssertionError(arguments)

    with pytest.raises(CompanionSourceError, match=message):
        verify_sources(tmp_path, lock, git=git, require_present=False)


def test_extra_fields_are_rejected() -> None:
    with pytest.raises(ValueError):
        CompanionLock.model_validate(
            {**admitted_lock().model_dump(), "unexpected": True}
        )
