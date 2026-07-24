"""The rendered Compose bundle enforces the appliance's isolation invariants."""

import pytest

from aegis.deploy.compose import RUNTIME_SOCKET, render_compose
from aegis.deploy.config import validate_config
from aegis.deploy.product import load_product_metadata

DIGEST = "sha256:" + "a" * 64


def _digests() -> dict[str, str]:
    return {
        name: DIGEST
        for name in ("aegis-control", "herdr", "qmd", "openviking", "hermes-gateway")
    }


def _render(hermes: bool = True):
    product = load_product_metadata()
    config = validate_config(
        {"version": 1, "services": {"hermes_gateway": hermes}, "secrets": {}}
    )
    return product, render_compose(product, config, _digests())


def test_no_service_publishes_a_public_port() -> None:
    _, bundle = _render()
    for service in bundle["services"].values():
        assert "ports" not in service


def test_only_control_plane_gets_the_runtime_socket() -> None:
    _, bundle = _render()
    for name, service in bundle["services"].items():
        mounts = service.get("volumes", [])
        has_socket = any("docker.sock" in mount for mount in mounts)
        assert has_socket == (name == "aegis-control")


def test_no_privileged_host_or_device_options() -> None:
    _, bundle = _render()
    for service in bundle["services"].values():
        assert service.get("privileged") is not True
        assert "network_mode" not in service
        assert "devices" not in service
        assert service.get("cap_drop") == ["ALL"]
        assert "no-new-privileges:true" in service.get("security_opt", [])


def test_all_images_are_digest_pinned() -> None:
    _, bundle = _render()
    for service in bundle["services"].values():
        assert "@sha256:" in service["image"]


def test_every_service_carries_product_labels() -> None:
    product, bundle = _render()
    for service in bundle["services"].values():
        assert service["labels"][f"{product.label_prefix}.managed"] == "true"


def test_backend_network_is_private() -> None:
    _, bundle = _render()
    assert bundle["networks"]["backend"]["internal"] is True


def test_gateway_reaches_only_the_control_socket() -> None:
    _, bundle = _render(hermes=True)
    gateway = bundle["services"]["hermes-gateway"]
    mounts = gateway.get("volumes", [])
    assert any("control.sock" in mount for mount in mounts)
    assert all("docker.sock" not in mount for mount in mounts)
    assert RUNTIME_SOCKET not in " ".join(mounts)


def test_disabled_service_is_absent() -> None:
    _, bundle = _render(hermes=False)
    assert "hermes-gateway" not in bundle["services"]


def test_missing_digest_is_rejected() -> None:
    product = load_product_metadata()
    config = validate_config({"version": 1, "secrets": {}})
    with pytest.raises(ValueError, match="digest"):
        render_compose(product, config, {"aegis-control": DIGEST})
