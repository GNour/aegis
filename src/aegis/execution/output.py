"""Dual-path command output: compressed to the model, full to a protected artifact.

The worker image runs pinned RTK to compress supported command output for the model,
but Aegis always retains the complete raw stream as an owner-only artifact before
compression. This keeps token usage low without ever discarding evidence, and records
the byte savings (and RTK version) for the attempt.
"""

import os
from dataclasses import dataclass
from pathlib import Path


class FilesystemArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()

    def write_text(self, relative: str, content: str, mode: int = 0o600) -> Path:
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("artifact path escapes store root")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        os.chmod(path, mode)
        return path


@dataclass(frozen=True)
class CapturedOutput:
    model_text: str
    full_artifact: Path
    full_bytes: int
    model_bytes: int
    saved_bytes: int
    rtk_version: str | None = None


class OutputCapture:
    def __init__(self, artifact_store: FilesystemArtifactStore) -> None:
        self.artifact_store = artifact_store

    def record(
        self, command_id: str, full: str, compressed: str, rtk_version: str | None = None
    ) -> CapturedOutput:
        artifact = self.artifact_store.write_text(
            f"commands/{command_id}.log", full, mode=0o600
        )
        full_bytes = len(full.encode("utf-8"))
        model_bytes = len(compressed.encode("utf-8"))
        return CapturedOutput(
            model_text=compressed,
            full_artifact=artifact,
            full_bytes=full_bytes,
            model_bytes=model_bytes,
            saved_bytes=max(0, full_bytes - model_bytes),
            rtk_version=rtk_version,
        )
