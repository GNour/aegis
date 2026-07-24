"""Deterministic routing simulation over a fixture request. No state is created.

Rules evaluate in ascending priority order (spec 02 section 3). The first terminal
match selects a flow; non-terminal rules along the way may only add risk or required
gates, never grant capabilities or override a deterministic denial. The simulation
records every evaluated rule ID so the explanation is auditable and contains no hidden
model reasoning.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from aegis.config.catalog import Catalog, CatalogError, CompiledFlow


class SimulationError(CatalogError):
    """Raised when no terminal routing rule matches and no explicit flow was requested."""


@dataclass(frozen=True)
class SimulationResult:
    flow: CompiledFlow
    evaluated_rule_ids: tuple[str, ...]
    matched_rule_id: str | None
    added_risk: str | None
    added_gates: tuple[str, ...]


def _matches(when: Mapping[str, str], request: Mapping[str, object]) -> bool:
    return all(request.get(key) == value for key, value in when.items())


def simulate(catalog: Catalog, request: Mapping[str, object]) -> SimulationResult:
    """Evaluate routing rules (or an explicit flow request) against ``request``."""
    requested_flow = request.get("flow_id")
    if requested_flow is not None and requested_flow != "auto":
        return SimulationResult(
            flow=catalog.flow(str(requested_flow)),
            evaluated_rule_ids=(),
            matched_rule_id=None,
            added_risk=None,
            added_gates=(),
        )

    evaluated: list[str] = []
    added_risk: str | None = None
    added_gates: list[str] = []
    matched_id: str | None = None

    for rule in sorted(catalog.routing.rules, key=lambda r: r.priority):
        evaluated.append(rule.id)
        if not _matches(rule.when, request):
            continue
        if rule.add_risk is not None:
            added_risk = rule.add_risk
        added_gates.extend(rule.add_gates)
        if rule.terminal:
            matched_id = rule.id
            break

    if matched_id is None:
        raise SimulationError("no terminal routing rule matched the request")

    selected = next(rule for rule in catalog.routing.rules if rule.id == matched_id)
    assert selected.select_flow is not None  # enforced by RoutingRule.validate_terminal_shape
    return SimulationResult(
        flow=catalog.flow(selected.select_flow),
        evaluated_rule_ids=tuple(evaluated),
        matched_rule_id=matched_id,
        added_risk=added_risk,
        added_gates=tuple(added_gates),
    )
