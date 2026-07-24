"""Host preflight and idempotent reconciliation.

Preflight verifies the distribution, release, architecture, and required kernel/storage/
network features and fails closed on an unsupported host. Reconcile is idempotent: it
adopts existing service identities, directories, and the Compose service without
duplicating them, so re-running the installer on a partial install completes it safely.
"""

from dataclasses import dataclass, field
from typing import Protocol

from aegis.deploy.product import ProductMetadata

SUPPORTED_DISTRO = "ubuntu"
SUPPORTED_RELEASES = frozenset({"22.04", "24.04"})
SUPPORTED_ARCH = frozenset({"x86_64", "amd64", "aarch64", "arm64"})
MIN_DISK_GB = 10.0
SERVICE_IDENTITIES = ("agentops", "hermesops")


@dataclass(frozen=True)
class HostFacts:
    distro: str
    release: str
    arch: str
    has_systemd: bool
    has_cgroup_v2: bool
    has_userns: bool
    free_disk_gb: float
    has_outbound_https: bool


def preflight(facts: HostFacts) -> list[str]:
    """Return a list of blocking reasons; empty means the host is supported."""
    blockers: list[str] = []
    if facts.distro != SUPPORTED_DISTRO:
        blockers.append(f"unsupported distro: {facts.distro}")
    if facts.release not in SUPPORTED_RELEASES:
        blockers.append(f"unsupported release: {facts.release}")
    if facts.arch not in SUPPORTED_ARCH:
        blockers.append(f"unsupported architecture: {facts.arch}")
    if not facts.has_systemd:
        blockers.append("systemd is required")
    if not facts.has_cgroup_v2:
        blockers.append("cgroup v2 is required")
    if not facts.has_userns:
        blockers.append("user namespaces are required")
    if facts.free_disk_gb < MIN_DISK_GB:
        blockers.append(f"insufficient disk: {facts.free_disk_gb} GB < {MIN_DISK_GB} GB")
    if not facts.has_outbound_https:
        blockers.append("outbound HTTPS is required")
    return blockers


class Host(Protocol):
    identities: set[str]
    directories: set[str]
    services: set[str]


@dataclass
class FakeHost:
    identities: set[str] = field(default_factory=set)
    directories: set[str] = field(default_factory=set)
    services: set[str] = field(default_factory=set)


def reconcile(host: Host, product: ProductMetadata) -> list[str]:
    """Create anything missing; return the actions taken (empty on a complete install)."""
    actions: list[str] = []
    for identity in SERVICE_IDENTITIES:
        if identity not in host.identities:
            host.identities.add(identity)
            actions.append(f"create identity {identity}")
    for directory in product.directories().values():
        if directory not in host.directories:
            host.directories.add(directory)
            actions.append(f"create directory {directory}")
    if product.compose_project not in host.services:
        host.services.add(product.compose_project)
        actions.append(f"install compose service {product.compose_project}")
    return actions
