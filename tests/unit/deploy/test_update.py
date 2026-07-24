"""Updates verify, back up, replace by digest, and auto-roll back on failed readiness."""

import pytest

from aegis.deploy.release import ReleaseManifest, sign_manifest
from aegis.deploy.update import UpdateError, UpdateOrchestrator

SECRET = b"release-signing-secret"
DIGEST = "sha256:" + "a" * 64


def _manifest(version="0.5.0", rollback_safe=True) -> ReleaseManifest:
    return ReleaseManifest.model_validate(
        {
            "channel": "stable",
            "version": version,
            "image_digests": {"aegis-control": DIGEST},
            "migrations": (),
            "rollback_safe": rollback_safe,
            "docs": ("d",),
            "release_notes": "n",
            "sbom": "s",
            "required_tests_passed": True,
        }
    )


class FakeRegistry:
    def __init__(self, manifest, secret=SECRET, tamper=False) -> None:
        self._manifest = manifest
        self._sig = "bad" if tamper else sign_manifest(secret, manifest)

    def fetch(self, channel, version=None):
        return self._manifest, self._sig


class FakeDeployer:
    def __init__(self, *, readiness_ok=True) -> None:
        self.applied: list[str] = []
        self.pulled: list[str] = []
        self._readiness_ok = readiness_ok

    def pull(self, manifest) -> None:
        self.pulled.append(manifest.version)

    def apply(self, manifest) -> None:
        self.applied.append(manifest.version)

    def readiness(self) -> bool:
        return self._readiness_ok


class FakeBackup:
    def __init__(self) -> None:
        self.created = 0

    def create(self) -> str:
        self.created += 1
        return f"backup-{self.created}"


class FakeStore:
    def __init__(self, current) -> None:
        self._current = current
        self.recorded: list = []

    def current(self):
        return self._current

    def record(self, manifest) -> None:
        self._current = manifest
        self.recorded.append(manifest)


def _orch(registry, deployer, backup, store):
    return UpdateOrchestrator(
        registry=registry, deployer=deployer, backup=backup, store=store, secret=SECRET
    )


def test_bad_signature_aborts_before_apply() -> None:
    target = _manifest("0.5.0")
    deployer = FakeDeployer()
    orch = _orch(FakeRegistry(target, tamper=True), deployer, FakeBackup(), FakeStore(_manifest("0.4.0")))
    with pytest.raises(UpdateError, match="signature"):
        orch.update()
    assert deployer.applied == []


def test_successful_update_backs_up_and_records() -> None:
    target = _manifest("0.5.0")
    deployer = FakeDeployer(readiness_ok=True)
    backup = FakeBackup()
    store = FakeStore(_manifest("0.4.0"))
    result = _orch(FakeRegistry(target), deployer, backup, store).update()
    assert result.state == "updated"
    assert backup.created == 1
    assert deployer.pulled == ["0.5.0"]
    assert store.current().version == "0.5.0"


def test_failed_readiness_auto_rolls_back_when_safe() -> None:
    target = _manifest("0.5.0", rollback_safe=True)
    prior = _manifest("0.4.0")
    deployer = FakeDeployer(readiness_ok=False)
    store = FakeStore(prior)
    result = _orch(FakeRegistry(target), deployer, FakeBackup(), store).update()
    assert result.state == "rolled_back"
    assert deployer.applied == ["0.5.0", "0.4.0"]
    assert store.current().version == "0.4.0"


def test_failed_readiness_without_rollback_safe_leaves_failed() -> None:
    target = _manifest("0.5.0", rollback_safe=False)
    prior = _manifest("0.4.0")
    deployer = FakeDeployer(readiness_ok=False)
    store = FakeStore(prior)
    result = _orch(FakeRegistry(target), deployer, FakeBackup(), store).update()
    assert result.state == "failed"
    assert store.current().version == "0.4.0"


def test_downgrade_is_blocked_unless_allowed() -> None:
    target = _manifest("0.3.0")
    store = FakeStore(_manifest("0.4.0"))
    orch = _orch(FakeRegistry(target), FakeDeployer(), FakeBackup(), store)
    with pytest.raises(UpdateError, match="downgrade"):
        orch.update()
    result = orch.update(allow_downgrade=True)
    assert result.state == "updated"
