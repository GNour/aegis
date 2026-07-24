"""Exact, digest-verified, read-only skill bundles.

A worker receives only the skills its role declares, at the exact declared version,
copied into an ephemeral read-only bundle. Digests are verified against the registry
manifest before copying, registry paths are proven contained, and the resulting
bundle is stripped of all write bits so a worker cannot mutate shared skill sources.
"""

import hashlib
import os
import shutil
from pathlib import Path


def directory_digest(path: Path) -> str:
    """Deterministic SHA-256 over a directory's relative paths and file contents."""
    digest = hashlib.sha256()
    root = Path(path)
    for file in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = file.relative_to(root).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


class SkillRegistry:
    def __init__(self, root: Path, manifest: dict[str, dict[str, str]]) -> None:
        self.root = Path(root).resolve()
        self.manifest = manifest

    def _resolve(self, skill_id: str, version: str) -> tuple[Path, str]:
        record = self.manifest.get(skill_id)
        if record is None or record["version"] != version:
            raise ValueError(f"unknown skill version: {skill_id}@{version}")
        source = (self.root / record["path"]).resolve()
        if not source.is_relative_to(self.root):
            raise ValueError("skill path escapes registry")
        actual = directory_digest(source)
        if actual != record["digest"]:
            raise ValueError(f"digest mismatch: {skill_id}@{version}")
        return source, actual

    def digest_map(self, requested: dict[str, str]) -> dict[str, str]:
        """Return {skill_id: digest} for the requested skills, verifying each."""
        return {
            skill_id: self._resolve(skill_id, version)[1]
            for skill_id, version in sorted(requested.items())
        }

    def bundle(self, requested: dict[str, str], destination: Path) -> Path:
        destination = Path(destination)
        destination.mkdir(mode=0o700, parents=True)
        for skill_id, version in sorted(requested.items()):
            source, _ = self._resolve(skill_id, version)
            shutil.copytree(source, destination / skill_id)
        for path in sorted(destination.rglob("*"), reverse=True):
            os.chmod(path, 0o500 if path.is_dir() else 0o400)
        os.chmod(destination, 0o500)
        return destination
