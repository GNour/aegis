from aegis.policy.engine import PolicyInput, PolicyOutcome, evaluate


def test_low_risk_action_is_autonomous() -> None:
    decision = evaluate(PolicyInput(action="task.cancel", risk="low"))
    assert decision.outcome is PolicyOutcome.ALLOW_AUTONOMOUS


def test_high_risk_without_prior_approval_requires_approval() -> None:
    decision = evaluate(PolicyInput(action="task.cancel", risk="high"))
    assert decision.outcome is PolicyOutcome.REQUIRE_APPROVAL


def test_high_risk_with_prior_approval_does_not_require_approval_again() -> None:
    decision = evaluate(PolicyInput(action="task.cancel", risk="high", prior_approval=True))
    assert decision.outcome is not PolicyOutcome.REQUIRE_APPROVAL


def test_nondelegable_action_is_denied_even_with_prior_approval() -> None:
    decision = evaluate(
        PolicyInput(action="task.cancel.destructive", risk="low", prior_approval=True)
    )
    assert decision.outcome is PolicyOutcome.DENY_NONDELEGABLE


def test_ambiguous_request_requires_decision_regardless_of_risk() -> None:
    decision = evaluate(PolicyInput(action="task.create", risk="low", ambiguous=True))
    assert decision.outcome is PolicyOutcome.REQUIRE_DECISION


def test_broker_required_action_is_allowed_brokered() -> None:
    decision = evaluate(PolicyInput(action="task.enrich", risk="low", requires_broker=True))
    assert decision.outcome is PolicyOutcome.ALLOW_BROKERED


def test_ambiguous_outranks_nondelegable_and_approval() -> None:
    # Ambiguity is resolved (a DecisionRequest) before any deny/approval judgement is made.
    decision = evaluate(
        PolicyInput(action="task.cancel.destructive", risk="high", ambiguous=True)
    )
    assert decision.outcome is PolicyOutcome.REQUIRE_DECISION
