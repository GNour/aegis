"""Native-first resume with handoff fallback and no capability broadening."""

from datetime import UTC, datetime, timedelta

import pytest

from aegis.execution.herdr import AgentSession
from aegis.execution.recovery import (
    Failure,
    FailureClass,
    RecoveryError,
    ResumeOutcome,
    ResumeService,
    assert_not_broader,
)
from aegis.execution.workers import ModelCapability, build_worker_spec


class FakeResumer:
    def __init__(self, *, compatible: bool) -> None:
        self._compatible = compatible

    def compatible(self) -> bool:
        return self._compatible

    def resume(self, session_id: str) -> AgentSession:
        return AgentSession(herdr_id=session_id, native_id="ses_123", state="running")


def _spec(memory_mb: int = 2048, cpus: float = 2.0):
    return build_worker_spec(
        task_id="t1",
        runtime="opencode",
        role={"id": "python-dev"},
        capability={"profile": "worktree-write", "memory_mb": memory_mb, "cpus": cpus},
        model=ModelCapability(proxy_url="http://model-proxy.internal", capability="implementation"),
        workspace=("/tasks/t1", "/workspace", "rw"),
        skills=[("/skills/s1", "/skills", "ro")],
    )


def test_resume_prefers_native_session() -> None:
    service = ResumeService(resumer=FakeResumer(compatible=True), handoff_validator=lambda h: True)
    outcome = service.resume(
        session_id="pane-17", handoff={"ok": True}, replacement_spec=_spec(), prior_spec=_spec()
    )
    assert isinstance(outcome, ResumeOutcome)
    assert outcome.mode == "native"
    assert outcome.session is not None
    assert outcome.session.native_id == "ses_123"


def test_resume_falls_back_to_validated_handoff() -> None:
    service = ResumeService(resumer=FakeResumer(compatible=False), handoff_validator=lambda h: True)
    replacement = _spec()
    outcome = service.resume(
        session_id="pane-17", handoff={"ok": True}, replacement_spec=replacement, prior_spec=_spec()
    )
    assert outcome.mode == "handoff"
    assert outcome.replacement is replacement
    assert outcome.session is None


def test_resume_rejects_invalid_handoff() -> None:
    service = ResumeService(resumer=FakeResumer(compatible=False), handoff_validator=lambda h: False)
    with pytest.raises(RecoveryError, match="handoff"):
        service.resume(
            session_id="pane-17", handoff={}, replacement_spec=_spec(), prior_spec=_spec()
        )


def test_replacement_cannot_broaden_resources() -> None:
    # more memory than the prior attempt is broader -> rejected
    with pytest.raises(ValueError, match="broader"):
        assert_not_broader(_spec(memory_mb=4096), _spec(memory_mb=2048))


def test_replacement_cannot_add_environment_keys() -> None:
    prior = _spec()
    broader = prior.model_copy(update={"environment": {**prior.environment, "EXTRA": "x"}})
    with pytest.raises(ValueError, match="broader"):
        assert_not_broader(broader, prior)


def test_equal_spec_is_not_broader() -> None:
    assert_not_broader(_spec(), _spec()) is None


def test_resume_rejects_broader_replacement() -> None:
    service = ResumeService(resumer=FakeResumer(compatible=False), handoff_validator=lambda h: True)
    with pytest.raises(ValueError, match="broader"):
        service.resume(
            session_id="pane-17",
            handoff={"ok": True},
            replacement_spec=_spec(memory_mb=4096),
            prior_spec=_spec(memory_mb=2048),
        )


def test_credit_limit_waits_without_retry_loop(engine, credit_failure) -> None:
    result = engine.handle_failure(credit_failure)
    assert result.state == "waiting_quota"
    assert result.earliest_retry is not None
    assert result.earliest_retry > datetime.now(UTC)
    assert result.dispatch_now is False


def test_provider_outage_uses_bounded_backoff(engine) -> None:
    failure = Failure(failure_class=FailureClass.PROVIDER_OUTAGE, provider="anthropic", attempt=3)
    result = engine.handle_failure(failure)
    assert result.state == "waiting_provider"
    assert result.dispatch_now is False
    assert result.earliest_retry is not None
    assert result.earliest_retry <= datetime.now(UTC) + timedelta(hours=1)


def test_process_exit_dispatches_resume(engine) -> None:
    result = engine.handle_failure(Failure(failure_class=FailureClass.PROCESS_EXIT))
    assert result.state == "resuming"
    assert result.dispatch_now is True


def test_every_failure_class_is_classified(engine) -> None:
    for failure_class in FailureClass:
        result = engine.handle_failure(Failure(failure_class=failure_class))
        assert result.state
