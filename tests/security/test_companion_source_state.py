"""The installed companion submodules must match the admitted lock and be clean."""

import json
from pathlib import Path

import pytest

from aegis.companions.lock import CompanionLock, CompanionSourceError, verify_sources

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = REPO_ROOT / "config" / "companions.lock.json"


def load_lock() -> CompanionLock:
    return CompanionLock.model_validate_json(LOCK_PATH.read_text(encoding="utf-8"))


@pytest.mark.skipif(not LOCK_PATH.exists(), reason="companions lock not generated yet")
def test_installed_submodules_are_clean_and_pinned() -> None:
    verify_sources(REPO_ROOT, load_lock(), require_present=True)


@pytest.mark.skipif(not LOCK_PATH.exists(), reason="companions lock not generated yet")
def test_lock_uses_only_https_companion_urls() -> None:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    assert lock["promptx"]["source_url"] == "https://github.com/GNour/promptx.git"
    assert lock["subagents"]["source_url"] == "https://github.com/GNour/subagents.git"


@pytest.mark.skipif(not LOCK_PATH.exists(), reason="companions lock not generated yet")
def test_advanced_commit_is_rejected() -> None:
    lock = load_lock()
    tampered = lock.model_copy(
        update={"promptx": lock.promptx.model_copy(update={"source_commit": "f" * 40})}
    )
    with pytest.raises(CompanionSourceError, match="source commit mismatch"):
        verify_sources(REPO_ROOT, tampered, require_present=True)
