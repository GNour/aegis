"""Update orchestration with pre-upgrade backup and automatic rollback.

An update verifies the signed manifest, checks compatibility (blocking a downgrade unless
explicitly allowed), takes a pre-upgrade backup, pulls images by digest, applies the new
release, and checks readiness. When readiness fails it automatically rolls back to the
prior release if the manifest declares rollback safe; otherwise it stops in a failed state
for manual recovery, leaving the recorded manifest at the prior release.
"""

from dataclasses import dataclass
from typing import Protocol

from aegis.deploy.release import ReleaseError, ReleaseManifest, parse_version, verify_manifest


class UpdateError(RuntimeError):
    """Raised when an update cannot proceed (verification or compatibility)."""


class Registry(Protocol):
    def fetch(
        self, channel: str, version: str | None = None
    ) -> tuple[ReleaseManifest, str]: ...


class Deployer(Protocol):
    def pull(self, manifest: ReleaseManifest) -> None: ...
    def apply(self, manifest: ReleaseManifest) -> None: ...
    def readiness(self) -> bool: ...


class Backup(Protocol):
    def create(self) -> str: ...


class ManifestStore(Protocol):
    def current(self) -> ReleaseManifest | None: ...
    def record(self, manifest: ReleaseManifest) -> None: ...


@dataclass(frozen=True)
class UpdateResult:
    state: str  # "updated" | "rolled_back" | "failed"
    version: str
    backup_id: str | None = None


class UpdateOrchestrator:
    def __init__(
        self,
        *,
        registry: Registry,
        deployer: Deployer,
        backup: Backup,
        store: ManifestStore,
        secret: bytes,
    ) -> None:
        self._registry = registry
        self._deployer = deployer
        self._backup = backup
        self._store = store
        self._secret = secret

    def update(
        self,
        *,
        channel: str = "stable",
        version: str | None = None,
        allow_downgrade: bool = False,
    ) -> UpdateResult:
        manifest, signature = self._registry.fetch(channel, version)
        try:
            verify_manifest(self._secret, manifest, signature)
        except ReleaseError as error:
            raise UpdateError(str(error)) from error

        prior = self._store.current()
        if prior is not None and not allow_downgrade:
            if parse_version(manifest.version) < parse_version(prior.version):
                raise UpdateError("target is a downgrade; pass allow_downgrade to proceed")

        backup_id = self._backup.create()
        self._deployer.pull(manifest)
        self._deployer.apply(manifest)

        if self._deployer.readiness():
            self._store.record(manifest)
            return UpdateResult("updated", manifest.version, backup_id)

        if manifest.rollback_safe and prior is not None:
            self._deployer.apply(prior)
            self._store.record(prior)
            return UpdateResult("rolled_back", prior.version, backup_id)

        return UpdateResult("failed", manifest.version, backup_id)
