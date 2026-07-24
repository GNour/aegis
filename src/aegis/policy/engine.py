"""Deterministic policy evaluation (spec 02 section 4).

``evaluate`` is a pure function: given the actor, task, project, stage, action type,
canonical parameters, requested capability, sandbox facts, and prior-approval state, it
returns exactly one of the five policy outcomes. A model may classify intent elsewhere,
but this function never consults one — it is deterministic and auditable end to end.
``deny_nondelegable`` still creates an operator-visible escalation upstream; approval may
authorize a brokered equivalent but can never turn the denied raw operation itself into
an autonomous worker capability.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PolicyOutcome(StrEnum):
    ALLOW_AUTONOMOUS = "allow_autonomous"
    ALLOW_BROKERED = "allow_brokered"
    REQUIRE_DECISION = "require_decision"
    REQUIRE_APPROVAL = "require_approval"
    DENY_NONDELEGABLE = "deny_nondelegable"


# Raw operations that can never be granted directly, regardless of prior approval. An
# approval against one of these authorizes only a brokered equivalent chosen by the
# caller; it can never convert the raw action itself into an autonomous grant.
NONDELEGABLE_ACTIONS: frozenset[str] = frozenset(
    {
        "task.cancel.destructive",
        "task.credential.export",
    }
)


@dataclass(frozen=True)
class PolicyInput:
    action: str
    risk: str  # "low" | "medium" | "high"
    ambiguous: bool = False
    requires_broker: bool = False
    prior_approval: bool = False


@dataclass(frozen=True)
class PolicyDecision:
    outcome: PolicyOutcome
    reason: str


def evaluate(policy_input: PolicyInput) -> PolicyDecision:
    """Evaluate one policy input into exactly one outcome. Pure; no I/O."""
    if policy_input.ambiguous:
        return PolicyDecision(
            PolicyOutcome.REQUIRE_DECISION, "request is ambiguous or ties multiple flows"
        )
    if policy_input.action in NONDELEGABLE_ACTIONS:
        return PolicyDecision(
            PolicyOutcome.DENY_NONDELEGABLE, f"{policy_input.action} is never delegable"
        )
    if policy_input.risk == "high" and not policy_input.prior_approval:
        return PolicyDecision(
            PolicyOutcome.REQUIRE_APPROVAL, "high-risk action requires operator approval"
        )
    if policy_input.requires_broker:
        return PolicyDecision(
            PolicyOutcome.ALLOW_BROKERED, "action requires a brokered capability"
        )
    return PolicyDecision(PolicyOutcome.ALLOW_AUTONOMOUS, "action is low-risk and autonomous")
