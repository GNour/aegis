"""Render the appliance's private-network Docker Compose bundle.

All services run rootless, read-only, with all capabilities dropped and privilege
escalation disabled, on private networks that publish no public ports. Only the Aegis
control-plane container is granted the rootless runtime socket; worker, gateway, and
knowledge containers never receive it. The Hermes gateway reaches only the typed control
socket. Every image is pinned by immutable digest and every service carries product labels.
"""

from typing import Any

from aegis.deploy.config import ApplianceConfig
from aegis.deploy.product import ProductMetadata

# The agentops rootless Docker socket, mounted read-only into the control plane only.
RUNTIME_SOCKET = "/run/user/1000/docker.sock"

_KNOWLEDGE = ("qmd", "openviking")


def render_compose(
    product: ProductMetadata,
    config: ApplianceConfig,
    image_digests: dict[str, str],
) -> dict[str, Any]:
    def base(name: str, network: str) -> dict[str, Any]:
        digest = image_digests.get(name)
        if not digest:
            raise ValueError(f"missing image digest for service {name!r}")
        return {
            "image": product.image_ref(name, digest),
            "labels": product.labels({f"{product.label_prefix}.service": name}),
            "networks": [network],
            "restart": "unless-stopped",
            "read_only": True,
            "security_opt": ["no-new-privileges:true"],
            "cap_drop": ["ALL"],
        }

    services: dict[str, Any] = {}

    control = base("aegis-control", "backend")
    control["volumes"] = [
        f"{RUNTIME_SOCKET}:/run/docker.sock:ro",
        f"{product.data_dir}:/var/lib/aegis",
        f"{product.config_dir}:/etc/aegis:ro",
    ]
    services["aegis-control"] = control

    herdr = base("herdr", "backend")
    herdr["volumes"] = [f"{product.data_dir}/herdr:/var/lib/herdr"]
    services["herdr"] = herdr

    for name in _KNOWLEDGE:
        if getattr(config.services, name):
            service = base(name, "backend")
            service["volumes"] = [f"{product.data_dir}/{name}:/var/lib/{name}"]
            services[name] = service

    if config.services.hermes_gateway:
        gateway = base("hermes-gateway", "edge")
        # The gateway reaches only the typed control socket; never the runtime API.
        gateway["volumes"] = [f"{product.data_dir}/control.sock:/run/aegis/control.sock:ro"]
        services["hermes-gateway"] = gateway

    return {
        "name": product.compose_project,
        "networks": {
            "backend": {"internal": True},
            "edge": {},  # egress only (Telegram outbound polling); publishes no ports
        },
        "services": services,
        "volumes": {},
    }
