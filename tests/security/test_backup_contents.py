"""Backups include durable state and exclude rebuildable/disposable resources."""

import tarfile
from pathlib import Path

import pytest

from aegis.deploy.backup import BackupService


def _seed(root: Path) -> None:
    for name in ("state", "audit", "config", "knowledge", "openviking", "artifacts"):
        (root / name).mkdir(parents=True)
        (root / name / "f").write_text(name, encoding="utf-8")
    for name in ("qmd", "images", "worktrees", "services"):
        (root / name).mkdir(parents=True)
        (root / name / "f").write_text(name, encoding="utf-8")
    (root / "secrets").mkdir()
    (root / "secrets" / "token").write_text("sk-secret", encoding="utf-8")


def _members(archive: Path) -> set[str]:
    with tarfile.open(archive, "r:gz") as tar:
        return {name.split("/")[0] for name in tar.getnames() if "/" in name}


def test_excluded_classes_are_absent(tmp_path) -> None:
    source = tmp_path / "data"
    source.mkdir()
    _seed(source)
    archive = BackupService().create(source, tmp_path / "b.tar.gz")
    members = _members(archive)
    for excluded in ("qmd", "images", "worktrees", "services", "secrets"):
        assert excluded not in members


def test_included_classes_are_present(tmp_path) -> None:
    source = tmp_path / "data"
    source.mkdir()
    _seed(source)
    archive = BackupService().create(source, tmp_path / "b.tar.gz")
    members = _members(archive)
    for included in ("state", "audit", "config", "knowledge", "openviking", "artifacts"):
        assert included in members


def test_secret_backup_without_encrypted_destination_is_refused(tmp_path) -> None:
    source = tmp_path / "data"
    source.mkdir()
    _seed(source)
    with pytest.raises(ValueError, match="encrypted destination"):
        BackupService().create(
            source, tmp_path / "b.tar.gz", include_secrets=True, encrypted_destination=None
        )


def test_secret_backup_with_encrypted_destination_is_allowed(tmp_path) -> None:
    source = tmp_path / "data"
    source.mkdir()
    _seed(source)
    archive = BackupService().create(
        source,
        tmp_path / "b.tar.gz",
        include_secrets=True,
        encrypted_destination=tmp_path / "secrets.enc",
    )
    # main archive still excludes plaintext secrets
    assert "secrets" not in _members(archive)
    assert (tmp_path / "secrets.enc").exists()
