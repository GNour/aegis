"""Strict Subagents input contracts and Aegis compiled-role output contracts.

The input side (``SubagentsCatalog`` and friends) validates the catalog emitted by the
pinned Subagents package. Every advisory field (model hint, tools, skills, handoffs) is
carried but confers no authority. The output side (``CompiledCatalog``) is what Aegis
actually trusts: it replaces advisory hints with reviewed model aliases, a fixed typed
tool registry, exact skills, and a capability profile drawn from ``role-mappings.yaml``.
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

# The only tool identifiers Aegis will grant to a compiled role. Advisory upstream tool
# strings (Bash, Write, …) are never copied into compiled output.
ALLOWED_TOOLS = frozenset({"qmd_search", "qmd_get", "project_test"})


class StrictModel(BaseModel):
    # extra="forbid" fails closed on unknown fields; frozen gives immutability. We do
    # not set strict=True because it blocks list->tuple coercion when validating parsed
    # JSON/YAML, and field patterns/types already reject malformed values.
    model_config = ConfigDict(extra="forbid", frozen=True)


# ── input side: the pinned Subagents catalog ────────────────────────────────
class SkillProvenance(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
    source: str
    version: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    license: str = Field(min_length=1, max_length=128)


class AdvisoryHandoff(StrictModel):
    role_id: str
    reason: str = Field(min_length=1, max_length=500)
    required: bool


class SubagentsRole(StrictModel):
    id: str
    department_id: str
    name: str
    title: str
    description: str
    expertise: tuple[str, ...]
    invocation: str
    standards: tuple[str, ...]
    model_hint: str
    advisory_tools: tuple[str, ...]
    skills: tuple[SkillProvenance, ...]
    handoffs: tuple[AdvisoryHandoff, ...]


class SubagentsDepartment(StrictModel):
    id: str
    name: str


class SubagentsCatalog(StrictModel):
    package_version: str
    catalog_schema_version: str
    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    departments: tuple[SubagentsDepartment, ...]
    roles: tuple[SubagentsRole, ...]

    @model_validator(mode="after")
    def validate_graph(self) -> Self:
        department_ids = [item.id for item in self.departments]
        role_ids = [item.id for item in self.roles]
        if len(department_ids) != len(set(department_ids)):
            raise ValueError("duplicate department id")
        if len(role_ids) != len(set(role_ids)):
            raise ValueError("duplicate role id")
        if any(role.department_id not in department_ids for role in self.roles):
            raise ValueError("unresolved department")
        if any(
            handoff.role_id not in role_ids
            for role in self.roles
            for handoff in role.handoffs
        ):
            raise ValueError("unresolved handoff")
        return self


# ── reviewed mappings: advisory role -> Aegis authority ─────────────────────
class RoleMapping(StrictModel):
    model_alias: str
    capability_profile: str
    skills: tuple[str, ...]
    tools: tuple[str, ...]


class RoleMappings(StrictModel):
    schema_version: int = Field(ge=1, le=1)
    roles: dict[str, RoleMapping]


# ── output side: the compiled catalog Aegis trusts ──────────────────────────
class CompiledRole(StrictModel):
    id: str
    department_id: str
    name: str
    title: str
    description: str
    expertise: tuple[str, ...]
    invocation: str
    standards: tuple[str, ...]
    model_alias: str
    capability_profile: str
    skills: tuple[SkillProvenance, ...]
    tools: tuple[str, ...]
    handoffs: tuple[AdvisoryHandoff, ...]


class CompiledCatalog(StrictModel):
    schema_version: int = Field(ge=1, le=1)
    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_package_version: str
    source_catalog_schema_version: str
    roles: tuple[CompiledRole, ...]

    @classmethod
    def from_reviewed(
        cls, source: SubagentsCatalog, mappings: RoleMappings
    ) -> "CompiledCatalog":
        role_ids = {role.id for role in source.roles}
        compiled: list[CompiledRole] = []
        for role in source.roles:
            mapping = mappings.roles.get(role.id)
            if mapping is None:
                raise ValueError(f"no reviewed mapping for role {role.id}")
            provenance = {skill.id: skill for skill in role.skills}
            selected_skills: list[SkillProvenance] = []
            for skill_id in mapping.skills:
                if skill_id not in provenance:
                    raise ValueError(
                        f"role {role.id}: mapped skill {skill_id} absent from provenance"
                    )
                selected_skills.append(provenance[skill_id])
            unknown_tools = set(mapping.tools) - ALLOWED_TOOLS
            if unknown_tools:
                raise ValueError(
                    f"role {role.id}: tools outside registry {sorted(unknown_tools)}"
                )
            for handoff in role.handoffs:
                if handoff.role_id not in role_ids:
                    raise ValueError(f"role {role.id}: unresolved handoff {handoff.role_id}")
            compiled.append(
                CompiledRole(
                    id=role.id,
                    department_id=role.department_id,
                    name=role.name,
                    title=role.title,
                    description=role.description,
                    expertise=role.expertise,
                    invocation=role.invocation,
                    standards=role.standards,
                    model_alias=mapping.model_alias,
                    capability_profile=mapping.capability_profile,
                    # Sort skills/tools/handoffs by stable id for deterministic output.
                    skills=tuple(sorted(selected_skills, key=lambda s: s.id)),
                    tools=tuple(sorted(mapping.tools)),
                    handoffs=tuple(sorted(role.handoffs, key=lambda h: h.role_id)),
                )
            )
        return cls(
            schema_version=1,
            source_commit=source.source_commit,
            source_package_version=source.package_version,
            source_catalog_schema_version=source.catalog_schema_version,
            roles=tuple(sorted(compiled, key=lambda r: r.id)),
        )
