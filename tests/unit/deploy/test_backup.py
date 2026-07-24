"""Backups round-trip and detect tampering."""

from pathlib import Path

from aegis.deploy.backup import BackupService


def _seed_source(root: Path) -> None:
    (root / "state").mkdir(parents=True)
    (root / "state" / "state.db").write_text("db", encoding="utf-8")
    (root / "audit").mkdir()
    (root / "audit" / "seg-1.jsonl").write_text("event", encoding="utf-8")
    (root / "knowledge").mkdir()
    (root / "knowledge" / "brain.md").write_text("# facts", encoding="utf-8")
    # rebuildable / disposable -> excluded
    (root / "qmd").mkdir()
    (root / "qmd" / "index.bin").write_text("rebuildable", encoding="utf-8")
    (root / "worktrees").mkdir()
    (root / "worktrees" / "t1").mkdir()


def test_create_then_verify_succeeds(tmp_path) -> None:
    source = tmp_path / "data"
    source.mkdir()
    _seed_source(source)
    service = BackupService()
    archive = service.create(source, tmp_path / "backup.tar.gz")
    assert service.verify(archive) is True


def test_restore_reproduces_included_state(tmp_path) -> None:
    source = tmp_path / "data"
    source.mkdir()
    _seed_source(source)
    service = BackupService()
    archive = service.create(source, tmp_path / "backup.tar.gz")

    target = tmp_path / "restored"
    service.restore(archive, target)
    assert (target / "state" / "state.db").read_text() == "db"
    assert (target / "knowledge" / "brain.md").read_text() == "# facts"


def test_tampered_archive_fails_verify(tmp_path) -> None:
    source = tmp_path / "data"
    source.mkdir()
    _seed_source(source)
    service = BackupService()
    archive = service.create(source, tmp_path / "backup.tar.gz")

    data = bytearray(archive.read_bytes())
    data[-1] ^= 0xFF
    archive.write_bytes(bytes(data))
    assert service.verify(archive) is False
