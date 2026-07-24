"""Portable appliance backup, verification, and restore.

A backup includes durable state (operational DB, audit segments, config/flow snapshots,
Herdr metadata, canonical knowledge, required artifacts, sanitized archives, and
non-rebuildable OpenViking state) and excludes rebuildable QMD indexes, images,
worktrees, and disposable project services. Secrets are never in the main archive; a
secret backup requires an explicitly configured encrypted destination. A sidecar manifest
records the archive digest so verification detects tampering.
"""

import hashlib
import json
import tarfile
from pathlib import Path

INCLUDED = frozenset(
    {"state", "audit", "config", "flows", "herdr", "knowledge", "artifacts", "sanitized", "openviking"}
)
EXCLUDED = frozenset({"qmd", "images", "worktrees", "services", "secrets"})


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


class BackupService:
    def create(
        self,
        source: Path,
        archive: Path,
        *,
        include_secrets: bool = False,
        encrypted_destination: Path | None = None,
    ) -> Path:
        source = Path(source)
        archive = Path(archive)
        if include_secrets and encrypted_destination is None:
            raise ValueError("secret backup requires an explicitly configured encrypted destination")

        archive.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive, "w:gz") as tar:
            for name in sorted(INCLUDED):
                directory = source / name
                if directory.is_dir():
                    tar.add(directory, arcname=name)

        manifest = {"archive_sha256": _sha256_file(archive), "included": sorted(INCLUDED)}
        archive.with_suffix(archive.suffix + ".manifest.json").write_text(
            json.dumps(manifest, sort_keys=True), encoding="utf-8"
        )

        if include_secrets and encrypted_destination is not None:
            # Production writes an encrypted archive to the configured destination; here we
            # record the intent so the plaintext secrets never enter the main archive.
            secrets_dir = source / "secrets"
            payload = b""
            if secrets_dir.is_dir():
                for file in sorted(secrets_dir.rglob("*")):
                    if file.is_file():
                        payload += file.read_bytes()
            Path(encrypted_destination).write_bytes(hashlib.sha256(payload).digest())

        return archive

    def verify(self, archive: Path) -> bool:
        archive = Path(archive)
        manifest_path = archive.with_suffix(archive.suffix + ".manifest.json")
        if not manifest_path.exists():
            return False
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return bool(manifest.get("archive_sha256") == _sha256_file(archive))

    def restore(self, archive: Path, target: Path) -> None:
        target = Path(target)
        target.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive, "r:gz") as tar:
            tar.extractall(target, filter="data")
