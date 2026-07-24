"""Installer preflight fails closed on unsupported hosts; reconcile is idempotent."""

import pytest

from aegis.deploy.installer import HostFacts, FakeHost, preflight, reconcile
from aegis.deploy.product import load_product_metadata


def _ok_facts(**over) -> HostFacts:
    data = {
        "distro": "ubuntu",
        "release": "24.04",
        "arch": "x86_64",
        "has_systemd": True,
        "has_cgroup_v2": True,
        "has_userns": True,
        "free_disk_gb": 40.0,
        "has_outbound_https": True,
    }
    data.update(over)
    return HostFacts(**data)


def test_supported_host_passes_preflight() -> None:
    assert preflight(_ok_facts()) == []


@pytest.mark.parametrize(
    "over",
    [
        {"distro": "fedora"},
        {"release": "20.04"},
        {"arch": "riscv64"},
        {"has_systemd": False},
        {"has_cgroup_v2": False},
        {"has_userns": False},
        {"free_disk_gb": 1.0},
        {"has_outbound_https": False},
    ],
)
def test_unsupported_host_fails_closed(over) -> None:
    assert preflight(_ok_facts(**over)) != []


def test_reconcile_creates_missing_then_is_idempotent() -> None:
    product = load_product_metadata()
    host = FakeHost()
    first = reconcile(host, product)
    assert first  # created identities/dirs/service on first run
    second = reconcile(host, product)
    assert second == []  # nothing to do on a repeated install


def test_reconcile_adopts_existing_without_duplicating() -> None:
    product = load_product_metadata()
    host = FakeHost()
    host.identities.add("agentops")  # already present
    actions = reconcile(host, product)
    assert not any("agentops" in action for action in actions)
