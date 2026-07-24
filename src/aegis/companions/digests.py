"""Deterministic artifact and SBOM digests for the companion lock.

Digests are computed from committed/built content, never hand-entered. A companion's
``artifact_sha256`` is the SHA-256 of a normalized (reproducible) tar of its release
directory; its ``sbom_sha256`` is the SHA-256 of a deterministic SPDX document that
records the package identity, license, and that artifact digest.
"""

from __future__ import annotations

import io
import json
import tarfile
from hashlib import sha256
from pathlib import Path

_EPOCH = 0


def _iter_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file())


def deterministic_tar_bytes(root: Path) -> bytes:
    """Build a reproducible, uncompressed tar of ``root`` with normalized metadata."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for path in _iter_files(root):
            info = tarfile.TarInfo(name=path.relative_to(root).as_posix())
            data = path.read_bytes()
            info.size = len(data)
            info.mtime = _EPOCH
            info.mode = 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.type = tarfile.REGTYPE
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def artifact_sha256(root: Path) -> str:
    return sha256(deterministic_tar_bytes(root)).hexdigest()


def build_sbom(
    *,
    name: str,
    version: str,
    source_url: str,
    source_commit: str,
    license_spdx: str,
    artifact_digest: str,
) -> dict[str, object]:
    """A minimal, deterministic SPDX 2.3 document (no wall-clock timestamp)."""
    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"{name}-{version}",
        "documentNamespace": f"{source_url}#{source_commit}",
        "creationInfo": {
            "created": "1970-01-01T00:00:00Z",
            "creators": ["Tool: aegis-companions-1"],
        },
        "packages": [
            {
                "SPDXID": "SPDXRef-Package",
                "name": name,
                "versionInfo": version,
                "downloadLocation": source_url,
                "filesAnalyzed": False,
                "licenseConcluded": license_spdx,
                "licenseDeclared": license_spdx,
                "sourceInfo": f"git commit {source_commit}",
                "checksums": [
                    {"algorithm": "SHA256", "checksumValue": artifact_digest}
                ],
            }
        ],
    }


def canonical_json_bytes(data: object) -> bytes:
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def sbom_sha256(sbom: dict[str, object]) -> str:
    return sha256(canonical_json_bytes(sbom)).hexdigest()
