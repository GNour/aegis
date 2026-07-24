"""Routing simulation: deterministic selection, evaluated-rule trail, no state."""

from pathlib import Path

import pytest

from aegis.config.catalog import build_catalog
from aegis.config.simulate import SimulationError, simulate

REPO_ROOT = Path(__file__).resolve().parents[3]
CATALOG = build_catalog(REPO_ROOT / "config")


def test_auto_routing_selects_feature_delivery() -> None:
    result = simulate(CATALOG, {"project_id": "demo", "intent": "feature-delivery", "flow_id": "auto"})
    assert result.flow.doc.id == "feature-delivery"
    assert result.matched_rule_id == "feature-delivery-default"
    assert result.evaluated_rule_ids == ("feature-delivery-default",)


def test_explicit_flow_request_bypasses_routing_rules() -> None:
    result = simulate(CATALOG, {"flow_id": "feature-delivery"})
    assert result.flow.doc.id == "feature-delivery"
    assert result.evaluated_rule_ids == ()
    assert result.matched_rule_id is None


def test_unmatched_intent_raises() -> None:
    with pytest.raises(SimulationError, match="no terminal routing rule matched"):
        simulate(CATALOG, {"project_id": "demo", "intent": "unknown-intent", "flow_id": "auto"})


def test_simulation_creates_no_state() -> None:
    # Running simulate twice must not mutate the catalog or produce different results.
    first = simulate(CATALOG, {"intent": "feature-delivery", "flow_id": "auto"})
    second = simulate(CATALOG, {"intent": "feature-delivery", "flow_id": "auto"})
    assert first.flow.snapshot() == second.flow.snapshot()
