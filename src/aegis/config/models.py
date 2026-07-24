"""Strict, frozen document models for the versioned configuration catalog.

Every document under ``config/`` declares an API version, stable identifier, integer
version, and description (spec 02 section 1). References carry a required minimum
version. Flow and stage documents intentionally have no field capable of holding a
shell command or arbitrary executable string — ``extra="forbid"`` rejects any attempt
to smuggle one in, and cross-reference resolution happens in ``aegis.config.catalog``.
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from aegis.companions.subagents import ALLOWED_TOOLS
from aegis.domain.models import (
    CatalogIdentifier,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveInt,
    _ensure_catalog_identifier,
)

# A safety gate every flow must declare; it can never be omitted or removed.
MANDATORY_GATES: tuple[str, ...] = ("qa-verification",)

_SEMVER = r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$"


class StrictModel(BaseModel):
    # extra="forbid" fails closed on unknown fields (including any shell/command
    # field an author might try to add); frozen gives immutability. strict=True is
    # deliberately omitted: it blocks list->tuple coercion when validating parsed
    # YAML, and field patterns/types already reject malformed values.
    model_config = ConfigDict(extra="forbid", frozen=True)


class CatalogDocument(StrictModel):
    api_version: str = Field(pattern=r"^1$")
    id: CatalogIdentifier
    version: PositiveInt
    description: str = Field(min_length=1, max_length=500)


class Ref(StrictModel):
    """A reference to another versioned catalog document."""

    id: CatalogIdentifier
    min_version: PositiveInt = 1


class SkillRef(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
    version: str = Field(pattern=_SEMVER)


class Budgets(StrictModel):
    time_seconds: PositiveInt
    tokens: PositiveInt
    context_tokens: PositiveInt
    cost_usd: NonNegativeFloat
    retry_limit: NonNegativeInt
    attempt_limit: PositiveInt


class RetryPolicy(StrictModel):
    max_retries: NonNegativeInt
    backoff_seconds: NonNegativeInt


# ── models.yaml: the single document of approved model aliases ─────────────
class ModelAliasEntry(StrictModel):
    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=128)


class ModelAliasesDoc(CatalogDocument):
    aliases: dict[str, ModelAliasEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_alias_keys(self) -> Self:
        for key in self.aliases:
            _ensure_catalog_identifier(key)
        return self


# ── capabilities/*.yaml ──────────────────────────────────────────────────────
class CapabilityProfileDoc(CatalogDocument):
    tools: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_tools(self) -> Self:
        if len(set(self.tools)) != len(self.tools):
            raise ValueError("duplicate tool in capability profile")
        unknown = set(self.tools) - ALLOWED_TOOLS
        if unknown:
            raise ValueError(f"tools outside registry: {sorted(unknown)}")
        return self


# ── roles/*.yaml ─────────────────────────────────────────────────────────────
class RoleDoc(CatalogDocument):
    model_alias: CatalogIdentifier
    capability_profile: Ref
    skills: tuple[SkillRef, ...] = ()

    @model_validator(mode="after")
    def validate_skills_unique(self) -> Self:
        ids = [skill.id for skill in self.skills]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate skill id in role")
        return self


# ── stages/*.yaml ────────────────────────────────────────────────────────────
class StageDoc(CatalogDocument):
    purpose: str = Field(min_length=1, max_length=500)
    preconditions: tuple[str, ...] = ()
    completion_evidence: tuple[str, ...] = Field(min_length=1)
    role: Ref
    model_alias: CatalogIdentifier
    capability_profile: Ref
    skills: tuple[SkillRef, ...] = ()
    input_schema: CatalogIdentifier | None = None
    output_schema: CatalogIdentifier | None = None
    budgets: Budgets
    decision_required: bool = False
    approval_required: bool = False
    fallback_stage: CatalogIdentifier | None = None
    resume_supported: bool = True
    knowledge_required: bool = False
    artifact_requirements: tuple[str, ...] = ()
    cleanup_gate: bool = False

    @model_validator(mode="after")
    def validate_skills_unique(self) -> Self:
        ids = [skill.id for skill in self.skills]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate skill id in stage")
        if self.fallback_stage == self.id:
            raise ValueError("stage cannot fall back to itself")
        return self


# ── flows/*.yaml ─────────────────────────────────────────────────────────────
class StageRef(Ref):
    pass


class FlowDoc(CatalogDocument):
    allowed_callers: tuple[str, ...] = Field(min_length=1)
    accepted_intents: tuple[str, ...] = Field(min_length=1)
    input_schema: CatalogIdentifier
    stages: tuple[StageRef, ...] = Field(min_length=1)
    gates: tuple[str, ...] = Field(min_length=1)
    retry_policy: RetryPolicy
    fallback_flow: CatalogIdentifier | None = None
    completion_policy: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_flow(self) -> Self:
        stage_ids = [ref.id for ref in self.stages]
        if len(stage_ids) != len(set(stage_ids)):
            raise ValueError("duplicate stage reference in flow")
        if len(set(self.gates)) != len(self.gates):
            raise ValueError("duplicate gate in flow")
        missing = set(MANDATORY_GATES) - set(self.gates)
        if missing:
            raise ValueError(f"missing mandatory gate(s): {sorted(missing)}")
        if self.fallback_flow == self.id:
            raise ValueError("flow cannot fall back to itself")
        return self


# ── routing.yaml ─────────────────────────────────────────────────────────────
class RoutingRule(StrictModel):
    id: CatalogIdentifier
    priority: PositiveInt
    terminal: bool
    when: dict[str, str] = Field(default_factory=dict)
    select_flow: CatalogIdentifier | None = None
    add_risk: str | None = Field(default=None, max_length=64)
    add_gates: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_terminal_shape(self) -> Self:
        if self.terminal and self.select_flow is None:
            raise ValueError(f"terminal routing rule {self.id} requires select_flow")
        if not self.terminal and self.select_flow is not None:
            raise ValueError(f"non-terminal routing rule {self.id} cannot select a flow")
        return self


class RoutingDoc(CatalogDocument):
    rules: tuple[RoutingRule, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_rules(self) -> Self:
        ids = [rule.id for rule in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate routing rule id")
        priorities = [rule.priority for rule in self.rules]
        if len(priorities) != len(set(priorities)):
            raise ValueError("duplicate routing rule priority")
        return self
