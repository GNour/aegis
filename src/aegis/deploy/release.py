"""Signed release manifests and the publication gate.

A release manifest pins every image by immutable digest and declares migrations,
rollback safety, docs, release notes, SBOM, and test status. Verification rejects a bad
signature or any non-digest ("latest"/tag) image. The publication gate refuses to ship
when docs, release notes, SBOM, tests, images, digests, or a valid signature are absent.
"""

import hashlib
import hmac
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ReleaseError(RuntimeError):
    """Raised when a release manifest fails verification."""


class ReleaseManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    channel: Literal["stable", "edge"]
    version: str
    image_digests: dict[str, str]
    migrations: tuple[str, ...] = ()
    rollback_safe: bool
    docs: tuple[str, ...]
    release_notes: str
    sbom: str
    required_tests_passed: bool


def canonical_manifest(manifest: ReleaseManifest) -> bytes:
    return json.dumps(manifest.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def sign_manifest(secret: bytes, manifest: ReleaseManifest) -> str:
    return hmac.new(secret, canonical_manifest(manifest), hashlib.sha256).hexdigest()


def verify_signature(secret: bytes, manifest: ReleaseManifest, signature: str) -> bool:
    return hmac.compare_digest(sign_manifest(secret, manifest), signature)


def _digests_pinned(manifest: ReleaseManifest) -> bool:
    return bool(manifest.image_digests) and all(
        digest.startswith("sha256:") for digest in manifest.image_digests.values()
    )


def verify_manifest(secret: bytes, manifest: ReleaseManifest, signature: str) -> ReleaseManifest:
    if not verify_signature(secret, manifest, signature):
        raise ReleaseError("release manifest signature is invalid")
    if not _digests_pinned(manifest):
        raise ReleaseError("release images must be pinned by sha256 digest")
    return manifest


def publication_blockers(
    secret: bytes, manifest: ReleaseManifest, signature: str
) -> list[str]:
    blockers: list[str] = []
    if not manifest.release_notes:
        blockers.append("release_notes")
    if not manifest.docs:
        blockers.append("docs")
    if not manifest.sbom:
        blockers.append("sbom")
    if not manifest.required_tests_passed:
        blockers.append("tests")
    if not manifest.image_digests:
        blockers.append("images")
    elif not _digests_pinned(manifest):
        blockers.append("digests")
    if not verify_signature(secret, manifest, signature):
        blockers.append("signature")
    return blockers


def parse_version(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for chunk in version.split("-")[0].split("."):
        parts.append(int(chunk) if chunk.isdigit() else 0)
    return tuple(parts)
