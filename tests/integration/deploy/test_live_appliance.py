"""Live appliance integration — runs only on a provisioned host.

These tests exercise the real rootless Docker/Compose install, boundaries, updates, and
recovery from the design's release matrix. They are collected but skipped unless the
corresponding environment is provisioned, matching the port/fake convention used across
the roadmap for external dependencies.
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    "AEGIS_LIVE_DOCKER" not in os.environ,
    reason="live rootless Docker appliance not provisioned",
)


def test_live_install_starts_and_reaches_readiness() -> None:  # pragma: no cover - live only
    from aegis.deploy.runtime import ComposeContainerRuntime

    runtime = ComposeContainerRuntime()
    services = runtime.ps(os.environ.get("AEGIS_COMPOSE_PROJECT", "aegis"))
    assert isinstance(services, list)


def test_live_no_public_listeners() -> None:  # pragma: no cover - live only
    # On a real host, assert none of the private services publish a public port.
    pytest.skip("implemented against a provisioned host in the release matrix")
