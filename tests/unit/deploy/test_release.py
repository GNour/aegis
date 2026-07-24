"""Release manifests must be signed, digest-pinned, and complete to publish."""

import pytest

from aegis.deploy.release import (
    ReleaseError,
    ReleaseManifest,
    publication_blockers,
    sign_manifest,
    verify_manifest,
)

SECRET = b"release-signing-secret"
DIGEST = "sha256:" + "a" * 64


def _manifest(**over) -> ReleaseManifest:
    data = {
        "channel": "stable",
        "version": "0.5.0",
        "image_digests": {"aegis-control": DIGEST},
        "migrations": ("0001_init",),
        "rollback_safe": True,
        "docs": ("https://docs/install",),
        "release_notes": "first pilot",
        "sbom": "sbom.spdx.json",
        "required_tests_passed": True,
    }
    data.update(over)
    return ReleaseManifest.model_validate(data)


def test_valid_signed_manifest_verifies() -> None:
    m = _manifest()
    sig = sign_manifest(SECRET, m)
    assert verify_manifest(SECRET, m, sig) is m


def test_bad_signature_is_rejected() -> None:
    m = _manifest()
    with pytest.raises(ReleaseError, match="signature"):
        verify_manifest(SECRET, m, "deadbeef")


def test_mutable_latest_tag_is_rejected() -> None:
    m = _manifest(image_digests={"aegis-control": "latest"})
    sig = sign_manifest(SECRET, m)
    with pytest.raises(ReleaseError, match="digest"):
        verify_manifest(SECRET, m, sig)


def test_missing_digest_is_rejected() -> None:
    m = _manifest(image_digests={"aegis-control": "v0.5.0"})
    sig = sign_manifest(SECRET, m)
    with pytest.raises(ReleaseError, match="digest"):
        verify_manifest(SECRET, m, sig)


def test_publication_gate_passes_for_complete_release() -> None:
    m = _manifest()
    sig = sign_manifest(SECRET, m)
    assert publication_blockers(SECRET, m, sig) == []


@pytest.mark.parametrize(
    "over,blocker",
    [
        ({"release_notes": ""}, "release_notes"),
        ({"docs": ()}, "docs"),
        ({"sbom": ""}, "sbom"),
        ({"required_tests_passed": False}, "tests"),
        ({"image_digests": {}}, "images"),
    ],
)
def test_publication_gate_blocks_incomplete_release(over, blocker) -> None:
    m = _manifest(**over)
    sig = sign_manifest(SECRET, m)
    assert blocker in publication_blockers(SECRET, m, sig)


def test_publication_gate_blocks_unsigned_release() -> None:
    m = _manifest()
    assert "signature" in publication_blockers(SECRET, m, "bad")
