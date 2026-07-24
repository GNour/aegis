"""Failure classification and native-first resume.

Every failure signal maps to exactly one class in the recovery table
(docs/specs/05-recovery-audit-cleanup.md). Quota and outage classes wait with a
computed retry time and never spin a retry loop. Resume prefers the native runtime
session; when it is unavailable a replacement runs from the latest validated
handoff, and a replacement may never inherit broader resources than the attempt it
replaces.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Protocol

from aegis.execution.herdr import AgentSession
from aegis.execution.workers import WorkerSpec


class RecoveryError(RuntimeError):
    """A recovery precondition (e.g. a valid handoff) was not met."""


class FailureClass(str, Enum):
    PROCESS_EXIT = "process_exit"
    AEGIS_RESTART = "aegis_restart"
    VPS_REBOOT = "vps_reboot"
    CREDIT_LIMIT = "credit_limit"
    PROVIDER_OUTAGE = "provider_outage"
    HUMAN_DECISION = "human_decision"
    POLICY_DENIAL = "policy_denial"
    STATE_MISMATCH = "state_mismatch"


@dataclass(frozen=True)
class Failure:
    failure_class: FailureClass
    provider: str | None = None
    model: str | None = None
    reset_at: datetime | None = None
    attempt: int = 0
    detail: str = ""


@dataclass(frozen=True)
class RecoveryDecision:
    state: str
    dispatch_now: bool
    earliest_retry: datetime | None
    reason: str
    provider: str | None = None
    model: str | None = None


_Now = Callable[[], datetime]


def _default_now() -> datetime:
    return datetime.now(UTC)


class RecoveryEngine:
    def __init__(
        self,
        *,
        now: _Now = _default_now,
        default_quota_cooldown: timedelta = timedelta(hours=1),
        base_backoff: timedelta = timedelta(seconds=30),
        max_backoff: timedelta = timedelta(minutes=30),
    ) -> None:
        self._now = now
        self._default_quota_cooldown = default_quota_cooldown
        self._base_backoff = base_backoff
        self._max_backoff = max_backoff

    def handle_failure(self, failure: Failure) -> RecoveryDecision:
        handler = _HANDLERS[failure.failure_class]
        return handler(self, failure)

    # ── individual classifiers ──────────────────────────────────────────────
    def _process_exit(self, failure: Failure) -> RecoveryDecision:
        return RecoveryDecision("resuming", True, None, "inspect session then resume or replace")

    def _reconcile(self, failure: Failure) -> RecoveryDecision:
        return RecoveryDecision(
            "reconciling", False, None, "startup reconciliation before new admission"
        )

    def _credit_limit(self, failure: Failure) -> RecoveryDecision:
        retry = failure.reset_at or (self._now() + self._default_quota_cooldown)
        return RecoveryDecision(
            "waiting_quota", False, retry, "provider credit/quota limit", failure.provider, failure.model
        )

    def _provider_outage(self, failure: Failure) -> RecoveryDecision:
        backoff = min(self._base_backoff * (2**failure.attempt), self._max_backoff)
        return RecoveryDecision(
            "waiting_provider",
            False,
            self._now() + backoff,
            "provider outage; bounded backoff",
            failure.provider,
            failure.model,
        )

    def _human_decision(self, failure: Failure) -> RecoveryDecision:
        return RecoveryDecision("waiting_human", False, None, "human decision required")

    def _policy_denial(self, failure: Failure) -> RecoveryDecision:
        return RecoveryDecision("blocked", False, None, "policy denied the action")

    def _state_mismatch(self, failure: Failure) -> RecoveryDecision:
        return RecoveryDecision(
            "recovery_required", False, None, "state/resource mismatch; quarantine"
        )


_HANDLERS: dict[FailureClass, Callable[[RecoveryEngine, Failure], RecoveryDecision]] = {
    FailureClass.PROCESS_EXIT: RecoveryEngine._process_exit,
    FailureClass.AEGIS_RESTART: RecoveryEngine._reconcile,
    FailureClass.VPS_REBOOT: RecoveryEngine._reconcile,
    FailureClass.CREDIT_LIMIT: RecoveryEngine._credit_limit,
    FailureClass.PROVIDER_OUTAGE: RecoveryEngine._provider_outage,
    FailureClass.HUMAN_DECISION: RecoveryEngine._human_decision,
    FailureClass.POLICY_DENIAL: RecoveryEngine._policy_denial,
    FailureClass.STATE_MISMATCH: RecoveryEngine._state_mismatch,
}


def assert_not_broader(replacement: WorkerSpec, prior: WorkerSpec) -> None:
    """Raise if ``replacement`` grants anything broader than ``prior``."""
    if set(replacement.environment) - set(prior.environment):
        raise ValueError("replacement is broader: added environment keys")
    if replacement.network != prior.network:
        raise ValueError("replacement is broader: network differs")
    prior_mounts = {(source, target): mode for source, target, mode in prior.mounts}
    for source, target, mode in replacement.mounts:
        prior_mode = prior_mounts.get((source, target))
        if prior_mode is None:
            raise ValueError("replacement is broader: added mount")
        if prior_mode == "ro" and mode == "rw":
            raise ValueError("replacement is broader: mount escalated to rw")
    if set(prior.cap_drop) - set(replacement.cap_drop):
        raise ValueError("replacement is broader: fewer capabilities dropped")
    if replacement.memory_mb > prior.memory_mb or replacement.cpus > prior.cpus:
        raise ValueError("replacement is broader: larger resource limits")
    if not replacement.no_new_privileges or not replacement.read_only_root:
        raise ValueError("replacement is broader: weaker isolation flags")


@dataclass(frozen=True)
class ResumeOutcome:
    mode: str  # "native" | "handoff"
    session: AgentSession | None
    replacement: WorkerSpec | None


class _Resumer(Protocol):
    def compatible(self) -> bool: ...
    def resume(self, session_id: str) -> AgentSession: ...


class ResumeService:
    def __init__(
        self, *, resumer: _Resumer, handoff_validator: Callable[[object], bool]
    ) -> None:
        self._resumer = resumer
        self._validate = handoff_validator

    def resume(
        self,
        *,
        session_id: str | None,
        handoff: object,
        replacement_spec: WorkerSpec,
        prior_spec: WorkerSpec,
    ) -> ResumeOutcome:
        if session_id and self._resumer.compatible():
            return ResumeOutcome("native", self._resumer.resume(session_id), None)
        if not self._validate(handoff):
            raise RecoveryError("cannot resume: handoff failed validation")
        assert_not_broader(replacement_spec, prior_spec)
        return ResumeOutcome("handoff", None, replacement_spec)
